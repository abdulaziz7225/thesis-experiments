module memory-bandwidth-spin-tinygo

// TinyGo 0.40.0, -target=wasip1.
// Uses the official Spin Go SDK (github.com/spinframework/spin-go-sdk/v2).
// CGo layer exports fermyon:spin/inbound-http, accepted by Spin's HTTP trigger.
// wasip2 target is not used: TinyGo wasip2 hardwires wasi:cli/command world and
// cannot export wasi:http/incoming-handler without unsupported WIT tooling.
go 1.21

require github.com/spinframework/spin-go-sdk/v2 v2.2.1

require github.com/julienschmidt/httprouter v1.3.0 // indirect
