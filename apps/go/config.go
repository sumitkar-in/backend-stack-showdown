package main

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
)

type config struct {
	port      string
	poolSize  int32
	dsn       string
	jwtSecret []byte // nil => auth disabled (AUTH_MODE=none)
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func loadConfig() (config, error) {
	pool, err := strconv.Atoi(env("DB_POOL_TOTAL", "20"))
	if err != nil || pool < 1 {
		return config{}, fmt.Errorf("invalid DB_POOL_TOTAL")
	}
	u := url.URL{
		Scheme: "postgres",
		User:   url.UserPassword(env("DB_USER", "bench"), env("DB_PASSWORD", "")),
		Host:   env("DB_HOST", "postgres") + ":" + env("DB_PORT", "5432"),
		Path:   env("DB_NAME", "sensorpulse"),
	}
	cfg := config{port: env("PORT", "8080"), poolSize: int32(pool), dsn: u.String()}
	if env("AUTH_MODE", "none") == "jwt" {
		cfg.jwtSecret = []byte(env("JWT_SECRET", "bench-jwt-secret-local-only"))
	}
	return cfg, nil
}
