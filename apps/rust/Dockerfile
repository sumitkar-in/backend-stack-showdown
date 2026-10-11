# syntax=docker/dockerfile:1
ARG RUST_IMAGE=rust:1.98.0-slim
ARG RUNTIME_IMAGE=gcr.io/distroless/cc-debian12:nonroot

FROM ${RUST_IMAGE} AS build
WORKDIR /src
# Dependency layer: build a stub first so source edits don't rebuild crates.
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs \
 && cargo build --release $( [ -f Cargo.lock ] && echo --locked ) \
 && rm -rf src target/release/sensorpulse target/release/deps/sensorpulse*
COPY src ./src
RUN cargo build --release $( [ -f Cargo.lock ] && echo --locked )

FROM ${RUNTIME_IMAGE}
COPY --from=build /src/target/release/sensorpulse /sensorpulse
ENV TOKIO_WORKER_THREADS=2
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/sensorpulse"]
