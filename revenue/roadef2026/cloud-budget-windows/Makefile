CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic
PARENT ?= ../cloud-optimizer/source.zip

all: solver
build/main.cpp: build.py budget_windows.hpp $(PARENT)
	python3 build.py --parent $(PARENT)
solver: build/main.cpp
	$(CXX) $(CXXFLAGS) -Ibuild/vendor build/main.cpp -o solver
test-windows: test_windows.cpp budget_windows.hpp
	$(CXX) $(CXXFLAGS) test_windows.cpp -o test-windows
test: test-windows
	./test-windows
clean:
	rm -f solver test-windows
.PHONY: all test clean
