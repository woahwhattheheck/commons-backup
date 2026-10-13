FROM ubuntu:24.04 AS build
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*
COPY . /build/
RUN /bin/sh build.sh

FROM ubuntu:24.04
WORKDIR /home
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY . /home/
COPY --from=build /build/bin /home/bin
COPY --from=build /build/run.sh /build/supervisor.py /build/compare_checker.py /build/source-manifest.json /home/
COPY --from=build /build/attribution /home/attribution
RUN chmod +x /home/run.sh /home/bin/* \
    && chown -R 1006410000:1006410000 /home/
USER 1006410000
CMD ["sleep", "infinity"]
