package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

var bodyUnauthorized = []byte(`{"error":"unauthorized"}`)

// jwtMiddleware verifies an HS256 bearer token on every request (no caching of verified tokens).
// Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
// valid HMAC-SHA256 signature, integer exp in the future, non-empty sub.
func jwtMiddleware(secret []byte) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !verifyJWT(c.GetHeader("Authorization"), secret) {
			c.Writer.Header().Set("WWW-Authenticate", "Bearer")
			send(c, 401, bodyUnauthorized)
			c.Abort()
			return
		}
		c.Next()
	}
}

func verifyJWT(header string, secret []byte) bool {
	const prefix = "Bearer "
	if !strings.HasPrefix(header, prefix) {
		return false
	}
	tok := header[len(prefix):]
	i := strings.IndexByte(tok, '.')
	if i <= 0 {
		return false
	}
	j := strings.IndexByte(tok[i+1:], '.')
	if j <= 0 {
		return false
	}
	j += i + 1
	sigPart := tok[j+1:]
	if sigPart == "" || strings.IndexByte(sigPart, '.') >= 0 {
		return false
	}
	enc := base64.RawURLEncoding
	sig, err := enc.DecodeString(sigPart)
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(tok[:j]))
	if !hmac.Equal(mac.Sum(nil), sig) {
		return false
	}
	hb, err := enc.DecodeString(tok[:i])
	if err != nil {
		return false
	}
	var hdr struct {
		Alg string `json:"alg"`
	}
	if json.Unmarshal(hb, &hdr) != nil || hdr.Alg != "HS256" {
		return false
	}
	pb, err := enc.DecodeString(tok[i+1 : j])
	if err != nil {
		return false
	}
	var claims struct {
		Sub string `json:"sub"`
		Exp *int64 `json:"exp"` // a float or string exp fails to unmarshal => rejected
	}
	if json.Unmarshal(pb, &claims) != nil {
		return false
	}
	return claims.Sub != "" && claims.Exp != nil && *claims.Exp > time.Now().Unix()
}
