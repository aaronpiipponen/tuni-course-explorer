"""Fixed-size byte cache in one anonymous shared memory region with a cross-process lock.

The supervisor creates one region and one lock before it forks the workers, so every worker reads
and writes the same pages. Entries are stored as a key and a value in 4 KiB pages, indexed by an
open-addressing table keyed by a 64-bit digest. A hit compares the stored key bytes, so a digest
collision only costs a probe step. A page clock hands out free page runs, and a slot clock chooses
the entry to evict when no run is free. Values larger than the region are not stored. The region
lives exactly as long as the supervisor that created it.
"""

from __future__ import annotations

import hashlib
import mmap
import os
import struct
from multiprocessing.synchronize import Lock

_PAGE_SIZE = 4096
_HEADER_SIZE = 64
_HEADER = struct.Struct("<IIII")
_SLOT = struct.Struct("<B7xQIIII")
_SLOT_SIZE = 32
_EMPTY = 0
_LIVE = 1
_TOMBSTONE = 2


def _align(offset: int, alignment: int) -> int:
    return (offset + alignment - 1) // alignment * alignment


def _digest(key: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "little")


class SharedByteCache:
    """One anonymous shared memory region holding byte entries under byte keys."""

    def __init__(self, descriptor: int, mapping: mmap.mmap, lock: Lock) -> None:
        self._descriptor = descriptor
        self._mapping = mapping
        self._lock = lock
        header = _HEADER.unpack_from(self._mapping, 0)
        self._page_count = header[0]
        self._slot_count = header[1]
        self._slot_offset = _align(_HEADER_SIZE + self._page_count, 8)
        self._page_offset = _align(self._slot_offset + self._slot_count * _SLOT_SIZE, _PAGE_SIZE)
        self._key_offset = self._page_offset

    @classmethod
    def create(cls, size: int) -> SharedByteCache:
        """Allocate one region of at most the requested byte size and initialize its tables."""
        if size <= _PAGE_SIZE * 3:
            raise ValueError("a shared cache region must hold at least four pages")
        page_count = (size - _PAGE_SIZE) // (_PAGE_SIZE + 1 + _SLOT_SIZE)
        while True:
            slot_offset = _align(_HEADER_SIZE + page_count, 8)
            page_offset = _align(slot_offset + page_count * _SLOT_SIZE, _PAGE_SIZE)
            if page_offset + page_count * _PAGE_SIZE <= size:
                break
            page_count -= 1
        descriptor = os.memfd_create("course-explorer-shared-cache", os.MFD_CLOEXEC)
        os.ftruncate(descriptor, size)
        mapping = mmap.mmap(descriptor, size)
        _HEADER.pack_into(mapping, 0, page_count, page_count, 0, 0)
        return cls(descriptor, mapping, _create_lock())

    def get(self, key: bytes) -> bytes | None:
        """Return the stored value for one key, or ``None``."""
        digest = _digest(key)
        with self._lock:
            index = self._find(key, digest)
            if index is None:
                return None
            _state, _hash, start, _pages, key_length, value_length = self._read_slot(index)
            start_offset = self._key_offset + start * _PAGE_SIZE
            return bytes(
                self._mapping[start_offset + key_length : start_offset + key_length + value_length]
            )

    def put(self, key: bytes, value: bytes) -> None:
        """Store one value under one key, replacing an existing value and evicting clock entries."""
        needed = len(key) + len(value)
        if needed > self._page_count * _PAGE_SIZE:
            return
        digest = _digest(key)
        pages = (needed + _PAGE_SIZE - 1) // _PAGE_SIZE
        with self._lock:
            index = self._find(key, digest)
            if index is None:
                index = self._insertion_slot(digest)
                if index is None:
                    if not self._evict_one():
                        return
                    index = self._insertion_slot(digest)
                    if index is None:
                        return
            state, _hash, start, occupied, _key_length, value_length = self._read_slot(index)
            if state == _LIVE:
                payload = key + value
                if len(payload) <= occupied * _PAGE_SIZE:
                    start_offset = self._key_offset + start * _PAGE_SIZE
                    self._mapping[start_offset : start_offset + len(payload)] = payload
                    self._write_slot(index, _LIVE, digest, start, occupied, len(key), len(value))
                    return
                self._free(start, occupied)
                self._write_slot(index, _TOMBSTONE, 0, 0, 0, 0, 0)
                index = self._insertion_slot(digest)
            start = self._allocate(pages)
            if start is None:
                return
            start_offset = self._key_offset + start * _PAGE_SIZE
            self._mapping[start_offset : start_offset + needed] = key + value
            self._write_slot(index, _LIVE, digest, start, pages, len(key), len(value))

    def close(self) -> None:
        """Release the supervisor's mapping and descriptor."""
        self._mapping.close()
        os.close(self._descriptor)

    def _read_slot(self, index: int) -> tuple[int, int, int, int, int, int]:
        return _SLOT.unpack_from(self._mapping, self._slot_offset + index * _SLOT_SIZE)

    def _write_slot(
        self,
        index: int,
        state: int,
        digest: int,
        start: int,
        pages: int,
        key_length: int,
        value_length: int,
    ) -> None:
        _SLOT.pack_into(
            self._mapping,
            self._slot_offset + index * _SLOT_SIZE,
            state,
            digest,
            start,
            pages,
            key_length,
            value_length,
        )

    def _find(self, key: bytes, digest: int) -> int | None:
        """Return the slot index of a matching key, or ``None`` when it is absent."""
        index = digest % self._slot_count
        for _ in range(self._slot_count):
            state, stored, start, _pages, key_length, _value_length = self._read_slot(index)
            if state == _EMPTY:
                return None
            if state == _LIVE and stored == digest and key_length == len(key):
                start_offset = self._key_offset + start * _PAGE_SIZE
                if self._mapping[start_offset : start_offset + key_length] == key:
                    return index
            index = (index + 1) % self._slot_count
        return None

    def _insertion_slot(self, digest: int) -> int | None:
        """Return the first tombstone or empty slot on one key's probe chain."""
        index = digest % self._slot_count
        tombstone: int | None = None
        for _ in range(self._slot_count):
            state, _stored, _start, _pages, _key_length, _value_length = self._read_slot(index)
            if state == _EMPTY:
                return index if tombstone is None else tombstone
            if state == _TOMBSTONE and tombstone is None:
                tombstone = index
            index = (index + 1) % self._slot_count
        return tombstone

    def _allocate(self, pages: int) -> int | None:
        """Return the first free page run of the requested length, evicting clock entries as
        needed."""
        header = _HEADER.unpack_from(self._mapping, 0)
        hand = header[2]
        for _ in range(self._slot_count + 1):
            start = self._find_free_run(hand, pages)
            if start is not None:
                for page in range(start, start + pages):
                    self._mapping[_HEADER_SIZE + page] = 1
                _HEADER.pack_into(
                    self._mapping,
                    0,
                    self._page_count,
                    self._slot_count,
                    (start + pages) % self._page_count,
                    header[3],
                )
                return start
            if not self._evict_one():
                return None
            header = _HEADER.unpack_from(self._mapping, 0)
            hand = header[2]
        return None

    def _find_free_run(self, hand: int, pages: int) -> int | None:
        run = 0
        start = 0
        for offset in range(self._page_count):
            page = (hand + offset) % self._page_count
            if self._mapping[_HEADER_SIZE + page] == 0:
                if run == 0:
                    start = page
                run += 1
                if run == pages:
                    return start
            else:
                run = 0
        return None

    def _evict_one(self) -> bool:
        """Free the next live clock slot and return whether one was freed."""
        header = _HEADER.unpack_from(self._mapping, 0)
        index = header[3]
        for _ in range(self._slot_count):
            state, _digest_value, start, pages, _key_length, _value_length = self._read_slot(index)
            next_index = (index + 1) % self._slot_count
            _HEADER.pack_into(
                self._mapping,
                0,
                self._page_count,
                self._slot_count,
                header[2],
                next_index,
            )
            if state == _LIVE:
                self._free(start, pages)
                self._write_slot(index, _TOMBSTONE, 0, 0, 0, 0, 0)
                return True
            index = next_index
        return False

    def _free(self, start: int, pages: int) -> None:
        for page in range(start, start + pages):
            self._mapping[_HEADER_SIZE + page] = 0


def _create_lock() -> Lock:
    """Create one POSIX lock that the supervisor's forked children inherit."""
    import multiprocessing

    return multiprocessing.Lock()
