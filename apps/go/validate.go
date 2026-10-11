package main

import (
	"bytes"
	"encoding/json"
	"io"
	"regexp"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

var (
	reID     = regexp.MustCompile(`^[1-9][0-9]{0,17}$`)
	reDevice = regexp.MustCompile(`^[1-9][0-9]{0,8}$`)
	reUint   = regexp.MustCompile(`^[0-9]{1,4}$`)
	reTS     = regexp.MustCompile(`^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,3})?(Z|[+-][0-9]{2}:[0-9]{2})$`)
)

const maxBody = 1 << 20

// parseTS: RFC3339 with timezone and at most 3 fractional digits -> Asia/Kolkata.
func parseTS(s string) (time.Time, bool) {
	if !reTS.MatchString(s) {
		return time.Time{}, false
	}
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return time.Time{}, false
	}
	return t.In(ist), true
}

// one returns the query value only when the parameter appears exactly once.
func one(c *gin.Context, name string) (string, bool) {
	v := c.QueryArray(name)
	if len(v) != 1 {
		return "", false
	}
	return v[0], true
}

type deviceRange struct {
	device   int32
	from, to time.Time
}

func parseDeviceRange(c *gin.Context) (deviceRange, bool) {
	dev, ok1 := one(c, "deviceId")
	fromS, ok2 := one(c, "from")
	toS, ok3 := one(c, "to")
	if !ok1 || !ok2 || !ok3 || !reDevice.MatchString(dev) {
		return deviceRange{}, false
	}
	from, okF := parseTS(fromS)
	to, okT := parseTS(toS)
	if !okF || !okT || !from.Before(to) {
		return deviceRange{}, false
	}
	d, _ := strconv.ParseInt(dev, 10, 32)
	return deviceRange{int32(d), from, to}, true
}

// parsePaging: limit 1-100 (default 50), offset 0-1000 (default 0).
func parsePaging(c *gin.Context) (limit, offset int64, ok bool) {
	limS, offS := "50", "0"
	if _, present := c.GetQuery("limit"); present {
		if limS, ok = one(c, "limit"); !ok {
			return
		}
	}
	if _, present := c.GetQuery("offset"); present {
		if offS, ok = one(c, "offset"); !ok {
			return
		}
	}
	if !reUint.MatchString(limS) || !reUint.MatchString(offS) {
		return 0, 0, false
	}
	limit, _ = strconv.ParseInt(limS, 10, 64)
	offset, _ = strconv.ParseInt(offS, 10, 64)
	return limit, offset, limit >= 1 && limit <= 100 && offset <= 1000
}

func parseID(raw string) (int64, bool) {
	if !reID.MatchString(raw) {
		return 0, false
	}
	id, err := strconv.ParseInt(raw, 10, 64)
	return id, err == nil
}

// readJSON parses the body into generic values. Numbers stay json.Number so
// 2375.0 / 1e3 can be rejected as non-integers. false => malformed (400).
func readJSON(c *gin.Context) (any, bool) {
	raw, err := io.ReadAll(io.LimitReader(c.Request.Body, maxBody+1))
	if err != nil || len(raw) > maxBody {
		return nil, false
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return nil, false
	}
	if _, err := dec.Token(); err != io.EOF { // trailing data
		return nil, false
	}
	return v, true
}

func intField(m map[string]any, key string, lo, hi int64) (int64, bool) {
	n, ok := m[key].(json.Number)
	if !ok {
		return 0, false
	}
	v, err := strconv.ParseInt(string(n), 10, 64)
	return v, err == nil && v >= lo && v <= hi
}

// parseReading validates one reading object into pgx args: int32, int16, int16, time.Time.
func parseReading(v any) ([]any, bool) {
	m, ok := v.(map[string]any)
	if !ok {
		return nil, false
	}
	d, ok1 := intField(m, "deviceId", 1, 2147483647)
	t, ok2 := intField(m, "temperatureCenti", -5000, 10000)
	h, ok3 := intField(m, "humidityBp", 0, 10000)
	s, ok4 := m["observedAt"].(string)
	if !ok1 || !ok2 || !ok3 || !ok4 {
		return nil, false
	}
	at, ok := parseTS(s)
	if !ok {
		return nil, false
	}
	return []any{int32(d), int16(t), int16(h), at}, true
}

// parseBatch validates 1-100 readings and flattens args for the multi-row INSERT.
func parseBatch(v any) (args []any, count int, ok bool) {
	m, isMap := v.(map[string]any)
	if !isMap {
		return nil, 0, false
	}
	items, isList := m["readings"].([]any)
	if !isList || len(items) < 1 || len(items) > 100 {
		return nil, 0, false
	}
	args = make([]any, 0, len(items)*4)
	for _, it := range items {
		a, ok := parseReading(it)
		if !ok {
			return nil, 0, false
		}
		args = append(args, a...)
	}
	return args, len(items), true
}
