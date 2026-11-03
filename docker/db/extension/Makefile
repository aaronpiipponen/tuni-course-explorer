# Build the exact semantic scan extension with PGXS.
EXTENSION = course_embedding_search
MODULE_big = course_embedding_search
OBJS = course_embedding_search.o
DATA = course_embedding_search--1.0.sql
PG_CONFIG ?= pg_config
PG_CPPFLAGS += -I$(shell $(PG_CONFIG) --includedir-server)/extension
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
override CXXFLAGS += -O3 -ffp-contract=off
SHLIB_LINK += -lstdc++
