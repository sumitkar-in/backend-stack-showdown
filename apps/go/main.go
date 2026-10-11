package main

import (
	"context"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
)

func newAPI(pool *pgxpool.Pool, cfg config) *api {
	a := &api{pool: pool}
	if cfg.jwtSecret != nil {
		a.auth = jwtMiddleware(cfg.jwtSecret)
	}
	return a
}

func newRouter(a *api) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	gin.DefaultWriter = io.Discard
	r := gin.New() // no access log
	r.Use(gin.CustomRecovery(func(c *gin.Context, _ any) {
		internal(c)
		c.Abort()
	}))
	r.NoRoute(notFound) // unknown route and wrong method -> not_found
	a.register(r)
	return r
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	pool, err := newPool(ctx, cfg)
	if err != nil {
		log.Fatalf("database: %v", err)
	}
	defer pool.Close()

	srv := &http.Server{
		Addr:              "0.0.0.0:" + cfg.port,
		Handler:           newRouter(newAPI(pool, cfg)),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server: %v", err)
		}
	}()

	<-ctx.Done()
	shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdown); err != nil {
		log.Printf("shutdown: %v", err)
		os.Exit(1)
	}
}
