/** One binary minimum heap ordered by a caller comparator. */

/** One binary minimum heap whose comparator decides which value `pop` returns. */
export class MinHeap<T> {
  private readonly values: T[] = [];
  private readonly compare: (first: T, second: T) => number;

  constructor(compare: (first: T, second: T) => number) {
    this.compare = compare;
  }

  /** Return the number of queued values. */
  get size(): number {
    return this.values.length;
  }

  /** Add one value to the heap. */
  push(value: T): void {
    this.values.push(value);
    let index = this.values.length - 1;
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (this.compare(this.values[index], this.values[parent]) >= 0) {
        break;
      }
      const swap = this.values[index];
      this.values[index] = this.values[parent];
      this.values[parent] = swap;
      index = parent;
    }
  }

  /** Remove and return the smallest queued value. An empty heap throws. */
  pop(): T {
    if (this.values.length === 0) {
      throw new Error("cannot pop an empty heap");
    }
    const first = this.values[0];
    const last = this.values.pop();
    if (last === undefined) {
      throw new Error("cannot pop an empty heap");
    }
    if (this.values.length === 0) {
      return first;
    }
    this.values[0] = last;
    let index = 0;
    for (;;) {
      const left = index * 2 + 1;
      const right = left + 1;
      let smallest = index;
      if (
        left < this.values.length &&
        this.compare(this.values[left], this.values[smallest]) < 0
      ) {
        smallest = left;
      }
      if (
        right < this.values.length &&
        this.compare(this.values[right], this.values[smallest]) < 0
      ) {
        smallest = right;
      }
      if (smallest === index) {
        return first;
      }
      const swap = this.values[index];
      this.values[index] = this.values[smallest];
      this.values[smallest] = swap;
      index = smallest;
    }
  }
}
