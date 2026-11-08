// Package redirect is a listener wrapper for Caddy: a plain HTTP request on the HTTPS port gets a temporary redirect
// to the same address over HTTPS, which browsers don't store. Caddy's own http_redirect answers with a permanent
// redirect without cache headers, which browsers keep: once HTTPS is turned off, the addresses opened meanwhile
// would still go to HTTPS and fail.
package redirect

import (
	"bufio"
	"bytes"
	"errors"
	"io"
	"net"
	"net/http"

	"github.com/caddyserver/caddy/v2"
	"github.com/caddyserver/caddy/v2/caddyconfig/caddyfile"
)

func init() {
	caddy.RegisterModule(Redirect{})
}

// Redirect is used in the Caddyfile as `candidate_redirect`, before `tls` in listener_wrappers.
type Redirect struct{}

func (Redirect) CaddyModule() caddy.ModuleInfo {
	return caddy.ModuleInfo{
		ID:  "caddy.listeners.candidate_redirect",
		New: func() caddy.Module { return new(Redirect) },
	}
}

func (r *Redirect) UnmarshalCaddyfile(d *caddyfile.Dispenser) error {
	d.Next()
	if d.NextArg() {
		return d.ArgErr()
	}
	return nil
}

func (r *Redirect) WrapListener(l net.Listener) net.Listener {
	return &listener{l}
}

type listener struct {
	net.Listener
}

func (l *listener) Accept() (net.Conn, error) {
	c, err := l.Listener.Accept()
	if err != nil {
		return nil, err
	}
	return &conn{Conn: c, r: bufio.NewReader(c)}, nil
}

type conn struct {
	net.Conn
	r       *bufio.Reader
	checked bool
}

// A request line starts with an uppercase method ("GET /"); a TLS handshake starts with the byte 0x16
func looksLikeHTTP(b []byte) bool {
	for i, c := range b {
		if c == ' ' && i > 0 {
			return true
		}
		if c < 'A' || c > 'Z' {
			return false
		}
	}
	return true
}

func (c *conn) Read(p []byte) (int, error) {
	if c.checked {
		return c.r.Read(p)
	}
	c.checked = true
	first, err := c.r.Peek(5)
	if err != nil || !looksLikeHTTP(first) {
		return c.r.Read(p)
	}
	buffered, _ := c.r.Peek(c.r.Buffered())
	// Requests larger than this are not redirected
	c.r.Reset(io.LimitReader(io.MultiReader(bytes.NewReader(buffered), c.Conn), 1<<20))
	req, err := http.ReadRequest(c.r)
	if err != nil {
		return 0, errors.New("unreadable HTTP request on the HTTPS port")
	}
	header := http.Header{}
	header.Set("Location", "https://"+req.Host+req.URL.RequestURI())
	header.Set("Cache-Control", "no-store")
	header.Set("Connection", "close")
	response := &http.Response{
		Proto: "HTTP/1.1", ProtoMajor: 1, ProtoMinor: 1,
		Status: "307 Temporary Redirect", StatusCode: http.StatusTemporaryRedirect,
		Header: header, ContentLength: 0,
	}
	if err := response.Write(c.Conn); err != nil {
		return 0, errors.New("unable to write the redirect to HTTPS")
	}
	return 0, errors.New("plain HTTP request on the HTTPS port redirected")
}

var (
	_ caddy.ListenerWrapper = (*Redirect)(nil)
	_ caddyfile.Unmarshaler = (*Redirect)(nil)
)
