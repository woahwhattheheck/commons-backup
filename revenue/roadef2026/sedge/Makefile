CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic

solver: main.cpp
	$(CXX) $(CXXFLAGS) -Ivendor main.cpp -o solver

.PHONY: clean
clean:
	rm -f solver
