package main

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

const contentJSON = "application/json"

var (
	bodyHealth = []byte(`{"status":"ok"}`)
	bodyBad    = []byte(`{"error":"bad_request"}`)
	bodyNotFnd = []byte(`{"error":"not_found"}`)
	bodyInvld  = []byte(`{"error":"validation_error"}`)
	bodyInt    = []byte(`{"error":"internal"}`)
)

// send always sets Content-Length so large bodies are never chunked.
func send(c *gin.Context, status int, body []byte) {
	c.Writer.Header().Set("Content-Length", strconv.Itoa(len(body)))
	c.Data(status, contentJSON, body)
}

func sendJSON(c *gin.Context, status int, v any) {
	b, err := json.Marshal(v)
	if err != nil {
		send(c, http.StatusInternalServerError, bodyInt)
		return
	}
	send(c, status, b)
}

func badRequest(c *gin.Context) { send(c, http.StatusBadRequest, bodyBad) }
func notFound(c *gin.Context)   { send(c, http.StatusNotFound, bodyNotFnd) }
func invalid(c *gin.Context)    { send(c, http.StatusUnprocessableEntity, bodyInvld) }
func internal(c *gin.Context)   { send(c, http.StatusInternalServerError, bodyInt) }
