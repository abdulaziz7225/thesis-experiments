module http-fanout-spin-tinygo

// TinyGo 0.40.0, -target=wasip1.
// Uses the official Spin Go SDK (github.com/spinframework/spin-go-sdk/v2).
// CGo layer exports fermyon:spin/inbound-http, accepted by Spin's HTTP trigger.
// Outbound HTTP fan-out: spinhttp.Send is blocking per-call but TinyGo's
// Asyncify scheduler lets goroutines drive multiple concurrent outbound
// requests cooperatively in a single Wasmtime instance.
go 1.21

require github.com/spinframework/spin-go-sdk/v2 v2.2.1

require github.com/julienschmidt/httprouter v1.3.0 // indirect
