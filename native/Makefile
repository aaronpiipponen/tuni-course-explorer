# Build the native serving libraries that the serving process loads, and the test-only fixture
# library from the same units.
CXX ?= g++
# -ffp-contract=off keeps each multiply and add separately rounded, so the compiled arithmetic keeps
# the scalar order and result that the scorer documents.
CXXFLAGS ?= -std=c++17 -O3 -ffp-contract=off -fPIC

all: libcourse_recommendation.so libcourse_prerequisite.so libcourse_lookup.so

libcourse_recommendation.so: scorer.cpp
	$(CXX) $(CXXFLAGS) -shared -o $@ $<

libcourse_lookup.so: lookup.cpp
	$(CXX) $(CXXFLAGS) -shared -o $@ $<

PREREQUISITE_SOURCES = compiler.cpp identity.cpp projector.cpp structure_view.cpp writer.cpp \
	evaluator.cpp api.cpp library_api.cpp pgloader.cpp

libcourse_prerequisite.so: $(PREREQUISITE_SOURCES) $(wildcard *.h)
	$(CXX) $(CXXFLAGS) -shared -o $@ $(PREREQUISITE_SOURCES) -lpq

# The fixture library compiles the same identity, projection, record-view and bundle units without
# the database loader or evaluator, so `fixture_reader.cpp` needs no service fact source.
FIXTURE_SOURCES = fixture_reader.cpp fixture_api.cpp library_api.cpp identity.cpp projector.cpp \
	structure_view.cpp writer.cpp

libcourse_prerequisite_fixtures.so: $(FIXTURE_SOURCES) $(wildcard *.h)
	$(CXX) $(CXXFLAGS) -shared -o $@ $(FIXTURE_SOURCES)

fixtures: libcourse_prerequisite_fixtures.so

clean:
	rm -f libcourse_recommendation.so libcourse_prerequisite.so libcourse_lookup.so \
		libcourse_prerequisite_fixtures.so
