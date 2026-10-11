# syntax=docker/dockerfile:1
ARG MAVEN_IMAGE=maven:3.9-eclipse-temurin-21
ARG RUNTIME_IMAGE=eclipse-temurin:21-jre

FROM ${MAVEN_IMAGE} AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -B -q -DskipTests package

FROM ${RUNTIME_IMAGE}
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /src/target/sensorpulse.jar app.jar
USER 10001
EXPOSE 8080
# JAVA_TOOL_OPTIONS (ActiveProcessorCount, MaxRAMPercentage) is set by compose.
ENTRYPOINT ["java", "-Xss512k", "-jar", "app.jar"]
