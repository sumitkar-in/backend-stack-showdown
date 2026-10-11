package main

import (
	"fmt"
	"strings"
	"sync"
)

const (
	sqlByID = "SELECT id, device_id, temperature_centi, humidity_bp, observed_at " +
		"FROM readings WHERE id = $1"
	sqlList = "SELECT id, device_id, temperature_centi, humidity_bp, observed_at " +
		"FROM readings " +
		"WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3 " +
		"ORDER BY observed_at DESC, id DESC LIMIT $4 OFFSET $5"
	sqlStats = "SELECT COUNT(*)::bigint AS count, " +
		"COALESCE(SUM(temperature_centi), 0)::bigint AS temperature_sum_centi, " +
		"COALESCE(SUM(humidity_bp), 0)::bigint AS humidity_sum_bp, " +
		"MIN(temperature_centi) AS temperature_min_centi, " +
		"MAX(temperature_centi) AS temperature_max_centi " +
		"FROM readings WHERE device_id = $1 AND observed_at >= $2 AND observed_at < $3"
	sqlInsert = "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) " +
		"VALUES ($1, $2, $3, $4) " +
		"RETURNING id, device_id, temperature_centi, humidity_bp, observed_at"
	sqlBatchHead = "INSERT INTO readings (device_id, temperature_centi, humidity_bp, observed_at) VALUES "
)

var batchCache sync.Map // int -> string

// sqlBatch returns one multi-row INSERT with n parameter groups (atomic), cached per size.
func sqlBatch(n int) string {
	if v, ok := batchCache.Load(n); ok {
		return v.(string)
	}
	groups := make([]string, n)
	for i := range groups {
		b := i * 4
		groups[i] = fmt.Sprintf("($%d,$%d,$%d,$%d)", b+1, b+2, b+3, b+4)
	}
	s := sqlBatchHead + strings.Join(groups, ",")
	batchCache.Store(n, s)
	return s
}
