CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic

all: solver

solver: main.cpp vendor/rapidjson/document.h
	$(CXX) $(CXXFLAGS) -Ivendor main.cpp -o solver

clean:
	rm -f solver

.PHONY: all clean
