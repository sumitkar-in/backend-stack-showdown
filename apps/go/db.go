package main

import (
	"context"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// newPool builds a fixed-size pool (min == max) and opens every connection up front.
func newPool(ctx context.Context, cfg config) (*pgxpool.Pool, error) {
	pc, err := pgxpool.ParseConfig(cfg.dsn)
	if err != nil {
		return nil, err
	}
	pc.MaxConns = cfg.poolSize
	pc.MinConns = cfg.poolSize
	pc.MaxConnIdleTime = 24 * time.Hour // 0 would mean "expire immediately" in pgxpool
	pc.MaxConnLifetime = 24 * time.Hour
	pc.HealthCheckPeriod = time.Hour

	pool, err := pgxpool.NewWithConfig(ctx, pc)
	if err != nil {
		return nil, err
	}
	if err := warm(ctx, pool, int(cfg.poolSize)); err != nil {
		pool.Close()
		return nil, err
	}
	return pool, nil
}

// warm acquires n connections at once so all of them exist before traffic starts.
func warm(ctx context.Context, pool *pgxpool.Pool, n int) error {
	var wg sync.WaitGroup
	errs := make(chan error, n)
	conns := make(chan *pgxpool.Conn, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c, err := pool.Acquire(ctx)
			if err != nil {
				errs <- err
				return
			}
			conns <- c
		}()
	}
	wg.Wait()
	close(conns)
	for c := range conns {
		c.Release()
	}
	select {
	case err := <-errs:
		return err
	default:
		return nil
	}
}
