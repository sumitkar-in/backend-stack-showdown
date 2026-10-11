package main

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

const queryTimeout = 10 * time.Second

type api struct {
	pool *pgxpool.Pool
	auth gin.HandlerFunc // nil when AUTH_MODE=none
}

func (a *api) register(r *gin.Engine) {
	r.GET("/health", func(c *gin.Context) { send(c, http.StatusOK, bodyHealth) }) // no DB access
	// Everything except /health sits behind the JWT middleware when enabled; unknown routes stay 404.
	rg := r.Group("")
	if a.auth != nil {
		rg.Use(a.auth)
	}
	rg.GET("/readings/stats", a.stats) // before /readings/:id
	rg.GET("/readings/:id", a.getReading)
	rg.GET("/readings", a.list)
	rg.POST("/readings", a.create)
	rg.POST("/readings/batch", a.createBatch)
}

func scanReading(row pgx.Row) (reading, error) {
	var r reading
	var at time.Time
	if err := row.Scan(&r.ID, &r.DeviceID, &r.TemperatureCenti, &r.HumidityBp, &at); err != nil {
		return r, err
	}
	r.ObservedAt = formatTS(at)
	return r, nil
}

// constraintViolation: FK (23503) or CHECK (23514) -> 422.
func constraintViolation(err error) bool {
	var pe *pgconn.PgError
	return errors.As(err, &pe) && (pe.Code == "23503" || pe.Code == "23514")
}

func (a *api) getReading(c *gin.Context) {
	id, ok := parseID(c.Param("id"))
	if !ok {
		invalid(c)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), queryTimeout)
	defer cancel()
	r, err := scanReading(a.pool.QueryRow(ctx, sqlByID, id))
	switch {
	case errors.Is(err, pgx.ErrNoRows):
		notFound(c)
	case err != nil:
		internal(c)
	default:
		sendJSON(c, http.StatusOK, r)
	}
}

func (a *api) list(c *gin.Context) {
	dr, ok := parseDeviceRange(c)
	limit, offset, okP := parsePaging(c)
	if !ok || !okP {
		invalid(c)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), queryTimeout)
	defer cancel()
	rows, err := a.pool.Query(ctx, sqlList, dr.device, dr.from, dr.to, limit, offset)
	if err != nil {
		internal(c)
		return
	}
	defer rows.Close()
	items := make([]reading, 0, limit)
	for rows.Next() {
		r, err := scanReading(rows)
		if err != nil {
			internal(c)
			return
		}
		items = append(items, r)
	}
	if rows.Err() != nil {
		internal(c)
		return
	}
	sendJSON(c, http.StatusOK, listResponse{Items: items, Limit: limit, Offset: offset})
}

func (a *api) stats(c *gin.Context) {
	dr, ok := parseDeviceRange(c)
	if !ok {
		invalid(c)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), queryTimeout)
	defer cancel()
	s := statsResponse{DeviceID: dr.device}
	err := a.pool.QueryRow(ctx, sqlStats, dr.device, dr.from, dr.to).
		Scan(&s.Count, &s.TemperatureSumCenti, &s.HumiditySumBp, &s.TemperatureMinCenti, &s.TemperatureMaxCenti)
	if err != nil {
		internal(c)
		return
	}
	sendJSON(c, http.StatusOK, s)
}

func (a *api) create(c *gin.Context) {
	body, ok := readJSON(c)
	if !ok {
		badRequest(c)
		return
	}
	args, ok := parseReading(body)
	if !ok {
		invalid(c)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), queryTimeout)
	defer cancel()
	r, err := scanReading(a.pool.QueryRow(ctx, sqlInsert, args...))
	switch {
	case err == nil:
		sendJSON(c, http.StatusCreated, r)
	case constraintViolation(err):
		invalid(c)
	default:
		internal(c)
	}
}

func (a *api) createBatch(c *gin.Context) {
	body, ok := readJSON(c)
	if !ok {
		badRequest(c)
		return
	}
	if _, isObj := body.(map[string]any); !isObj {
		badRequest(c)
		return
	}
	args, n, ok := parseBatch(body)
	if !ok {
		invalid(c)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), queryTimeout)
	defer cancel()
	_, err := a.pool.Exec(ctx, sqlBatch(n), args...)
	switch {
	case err == nil:
		sendJSON(c, http.StatusCreated, insertedResponse{Inserted: n})
	case constraintViolation(err):
		invalid(c)
	default:
		internal(c)
	}
}
