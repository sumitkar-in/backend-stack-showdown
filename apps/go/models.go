package main

import "time"

// Field order here fixes JSON key order.
type reading struct {
	ID               int64  `json:"id"`
	DeviceID         int32  `json:"deviceId"`
	TemperatureCenti int16  `json:"temperatureCenti"`
	HumidityBp       int16  `json:"humidityBp"`
	ObservedAt       string `json:"observedAt"`
}

type listResponse struct {
	Items  []reading `json:"items"`
	Limit  int64     `json:"limit"`
	Offset int64     `json:"offset"`
}

type statsResponse struct {
	DeviceID            int32  `json:"deviceId"`
	Count               int64  `json:"count"`
	TemperatureSumCenti int64  `json:"temperatureSumCenti"`
	HumiditySumBp       int64  `json:"humiditySumBp"`
	TemperatureMinCenti *int16 `json:"temperatureMinCenti"`
	TemperatureMaxCenti *int16 `json:"temperatureMaxCenti"`
}

type insertedResponse struct {
	Inserted int `json:"inserted"`
}

// ist is Asia/Kolkata as a fixed +05:30 zone (India has no DST), so no tzdata is needed in the distroless image.
var ist = time.FixedZone("IST", 5*3600+30*60)

// formatTS renders Asia/Kolkata with exactly 3 fractional digits and a +05:30 offset.
func formatTS(t time.Time) string {
	return t.In(ist).Format("2006-01-02T15:04:05.000-07:00")
}
