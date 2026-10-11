# syntax=docker/dockerfile:1
# Spring Boot 3.4 compiled ahead-of-time to a native executable with GraalVM (Mandrel-compatible community build).
ARG MAVEN_IMAGE=maven:3.9-eclipse-temurin-21
ARG GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21
ARG RUNTIME_IMAGE=debian:bookworm-slim

FROM ${MAVEN_IMAGE} AS maven

FROM ${GRAALVM_IMAGE} AS build
COPY --from=maven /usr/share/maven /usr/share/maven
ENV PATH=/usr/share/maven/bin:$PATH
WORKDIR /src
COPY pom.xml .
RUN mvn -B -q -Pnative dependency:go-offline -DskipTests || true
COPY src ./src
# Needs roughly 6+ GiB of RAM for the native-image step.
RUN mvn -B -q -Pnative -DskipTests native:compile

FROM ${RUNTIME_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends zlib1g \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /src/target/sensorpulse /app/sensorpulse
USER 10001
EXPOSE 8080
# Native images ignore JAVA_TOOL_OPTIONS; runtime flags come from NATIVE_OPTS (set by compose).
ENV NATIVE_OPTS="-Xmx2600m"
ENTRYPOINT ["sh", "-c", "exec /app/sensorpulse $NATIVE_OPTS"]
