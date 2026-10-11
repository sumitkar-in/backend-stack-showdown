# syntax=docker/dockerfile:1
ARG GO_IMAGE=golang:1.23
ARG RUNTIME_IMAGE=gcr.io/distroless/static-debian12:nonroot

FROM ${GO_IMAGE} AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/sensorpulse .

FROM ${RUNTIME_IMAGE}
COPY --from=build /out/sensorpulse /sensorpulse
ENV GIN_MODE=release GOMAXPROCS=2
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/sensorpulse"]
