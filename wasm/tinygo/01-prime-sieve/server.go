// WasmEdge socket layer for TinyGo WASM.
//
// Provides serveWasmEdge() as a drop-in for http.ListenAndServe().
// main.go is unmodified standard net/http handler code.
//
// WasmEdge's WASI socket extension (sock_open/bind/listen/accept) is called
// via //go:wasmimport; signatures match wasmedge_wasi_socket v0.5.5.

package main

import (
	"bytes"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"unsafe"
)

// ── WasmEdge socket imports ──────────────────────────────────────────────────

//go:wasmimport wasi_snapshot_preview1 sock_open
func sockOpen(af uint32, socktype uint32, fd unsafe.Pointer) uint32

//go:wasmimport wasi_snapshot_preview1 sock_bind
func sockBind(fd uint32, addr unsafe.Pointer, port uint32) uint32

//go:wasmimport wasi_snapshot_preview1 sock_listen
func sockListen(fd uint32, backlog uint32) uint32

//go:wasmimport wasi_snapshot_preview1 sock_accept
func sockAccept(fd uint32, conn unsafe.Pointer) uint32

//go:wasmimport wasi_snapshot_preview1 sock_recv
func sockRecv(fd uint32, iov unsafe.Pointer, iovlen uint32, flags uint32, n unsafe.Pointer, oflags unsafe.Pointer) uint32

//go:wasmimport wasi_snapshot_preview1 sock_send
func sockSend(fd uint32, iov unsafe.Pointer, iovlen uint32, flags uint32, n unsafe.Pointer) uint32

//go:wasmimport wasi_snapshot_preview1 sock_shutdown
func sockShutdown(fd uint32, how uint32) uint32

//go:wasmimport wasi_snapshot_preview1 fd_close
func fdClose(fd uint32) uint32

// ── ABI types (C repr, 32-bit WASM: pointer = usize = 4 bytes) ──────────────

type wasiAddr struct{ buf, size uint32 }   // WasiAddress { *u8, usize }
type wasiIov  struct{ buf, size uint32 }   // IovecRead/Write { *u8, usize }

const (
	afInet     uint32 = 1 // AddressFamily::Inet4 = 1 in WasmEdge
	sockStream uint32 = 2 // SocketType::Stream   = 2 in WasmEdge
)

// ── wasResponseWriter implements http.ResponseWriter ────────────────────────
type wasResponseWriter struct {
	h      http.Header
	body   bytes.Buffer
	status int
}

func (w *wasResponseWriter) Header() http.Header         { return w.h }
func (w *wasResponseWriter) WriteHeader(code int)        { w.status = code }
func (w *wasResponseWriter) Write(b []byte) (int, error) { return w.body.Write(b) }

// ── serveWasmEdge ────────────────────────────────────────────────────────────
func serveWasmEdge(addr string, h http.Handler) error {
	// Parse port from ":8080".
	colon := strings.LastIndex(addr, ":")
	port := uint32(0)
	for _, c := range addr[colon+1:] {
		port = port*10 + uint32(c-'0')
	}

	var lfd uint32
	if r := sockOpen(afInet, sockStream, unsafe.Pointer(&lfd)); r != 0 {
		return fmt.Errorf("sock_open: %d", r)
	}
	ip := [4]byte{}
	a := wasiAddr{uint32(uintptr(unsafe.Pointer(&ip[0]))), 4}
	if r := sockBind(lfd, unsafe.Pointer(&a), port); r != 0 {
		return fmt.Errorf("sock_bind: %d", r)
	}
	if r := sockListen(lfd, 128); r != 0 {
		return fmt.Errorf("sock_listen: %d", r)
	}

	for {
		var cfd uint32
		if r := sockAccept(lfd, unsafe.Pointer(&cfd)); r != 0 {
			fmt.Fprintf(os.Stderr, "sock_accept: %d\n", r)
			continue
		}
		serveConn(cfd, h)
	}
}

func serveConn(fd uint32, h http.Handler) {
	defer func() { sockShutdown(fd, 3); fdClose(fd) }()

	raw := recv(fd)
	if len(raw) == 0 {
		return
	}

	// Parse request line: "GET /path?query HTTP/1.1"
	line, _, _ := strings.Cut(string(raw), "\r\n")
	fields := strings.Fields(line)
	if len(fields) < 2 {
		return
	}
	u, err := url.Parse(fields[1])
	if err != nil {
		return
	}

	req := &http.Request{Method: fields[0], URL: u, Header: make(http.Header)}
	w   := &wasResponseWriter{h: make(http.Header), status: http.StatusOK}
	h.ServeHTTP(w, req)

	// Write response.
	body := w.body.Bytes()
	var hdr bytes.Buffer
	fmt.Fprintf(&hdr, "HTTP/1.1 %d %s\r\n", w.status, http.StatusText(w.status))
	for k, vs := range w.h {
		fmt.Fprintf(&hdr, "%s: %s\r\n", k, strings.Join(vs, ", "))
	}
	fmt.Fprintf(&hdr, "Content-Length: %d\r\nConnection: close\r\n\r\n", len(body))
	send(fd, append(hdr.Bytes(), body...))
}

// ── I/O helpers ──────────────────────────────────────────────────────────────
func recv(fd uint32) []byte {
	buf := make([]byte, 4096)
	var out []byte
	for {
		iov := wasiIov{uint32(uintptr(unsafe.Pointer(&buf[0]))), uint32(len(buf))}
		var n, of uint32
		if sockRecv(fd, unsafe.Pointer(&iov), 1, 0, unsafe.Pointer(&n), unsafe.Pointer(&of)) != 0 {
			break
		}
		out = append(out, buf[:n]...)
		if bytes.Contains(out, []byte("\r\n\r\n")) || n < uint32(len(buf)) {
			break
		}
	}
	return out
}

func send(fd uint32, data []byte) {
	for len(data) > 0 {
		iov := wasiIov{uint32(uintptr(unsafe.Pointer(&data[0]))), uint32(len(data))}
		var n uint32
		if sockSend(fd, unsafe.Pointer(&iov), 1, 0, unsafe.Pointer(&n)) != 0 || n == 0 {
			return
		}
		data = data[n:]
	}
}
