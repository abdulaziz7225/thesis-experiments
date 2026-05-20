module json-roundtrip-spin-tinygo

// TinyGo 0.40.0, -target=wasip1.
// Uses the official Spin Go SDK (github.com/spinframework/spin-go-sdk/v2).
// CGo layer exports fermyon:spin/inbound-http, accepted by Spin's HTTP trigger.
go 1.21

require github.com/spinframework/spin-go-sdk/v2 v2.2.1

require github.com/julienschmidt/httprouter v1.3.0 // indirect
