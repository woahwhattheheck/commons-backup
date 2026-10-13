FROM ubuntu:24.04
WORKDIR /home
COPY . /home/
RUN apt-get update && apt-get install -y --no-install-recommends g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && g++ -O3 -std=c++20 -Ivendor main.cpp -o solver \
    && chmod +x run.sh solver \
    && chown -R 1006410000:1006410000 /home/
USER 1006410000
CMD ["sleep", "infinity"]
