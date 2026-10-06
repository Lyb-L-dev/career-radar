# Ground truth for HTTP and session evaluation corrections

Verified: 2026-10-05. Scope: the five factual questions supplied from a synthetic MiMo evaluation of Career Radar. This is a documentation check, not a code, architecture, or security audit. No application code, configuration, or database was changed.

## 1. HTTP message syntax depends on the version

HTTP/1.1 uses a textual request/status start-line, CRLF-delimited fields, an empty line, and an optional body. A body can contain binary data; calling the entire message plain text is inaccurate. HTTP/2 uses binary frames and pseudo-header fields for control data, rather than an HTTP/1.1 start-line. HTTP/3 likewise sends HEADERS/DATA frames over QUIC streams and conveys control data with pseudo-header fields.

Sources: [RFC 9112 §§2.1, 3, 4](https://www.rfc-editor.org/rfc/rfc9112.html#section-2.1); [RFC 9113 §§4.1, 8.3](https://www.rfc-editor.org/rfc/rfc9113.html#section-4.1); [RFC 9114 §§4.1, 4.3](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.1).

## 2. GET/POST are semantic distinctions, not payload-location rules

- GET is safe and idempotent: the requested action is retrieval; incidental logging is permitted. Idempotence concerns the intended server effect, not identical response bytes.
- POST asks the resource to process the representation under its own semantics; creation is only one use. POST is not inherently safe/idempotent, although an endpoint can define idempotent processing.
- GET responses are cacheable unless controls say otherwise. POST responses can be cached with explicit freshness and Content-Location matching the target URI, for later GET/HEAD reuse; they cannot satisfy later POST requests.
- HTTP framing allows GET content, but it has no generally defined semantics and clients should not send it without prior origin support. Browser Fetch disallows GET bodies. POST can include query parameters as well as content.

Sources: [RFC 9110 §§9.2.1–9.3.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1); [RFC 9112 §3.2.1: origin-form includes an optional query for direct requests other than CONNECT/server-wide OPTIONS](https://www.rfc-editor.org/rfc/rfc9112.html#section-3.2.1); [MDN, Using Fetch: Setting a body](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#setting_a_body).

## 3. Browser Fetch does not let scripts directly set Cookie

Cookie is a forbidden request header. The browser selects applicable stored cookies and constructs the header. Use server Set-Cookie handling and Fetch credentials settings: same-origin is the default; include permits credentials on cross-origin requests. Cookie eligibility rules, including SameSite and browser cookie policy, still apply. For a credentialed cross-origin response to be exposed to JavaScript, the server must send Access-Control-Allow-Credentials: true and an explicit allowed origin rather than a wildcard. Credentials does not create an arbitrary cookie or override cookie restrictions.

Sources: [WHATWG Fetch, forbidden request-header and cookie handling](https://fetch.spec.whatwg.org/#forbidden-request-header); [MDN forbidden request headers](https://developer.mozilla.org/en-US/docs/Glossary/Forbidden_request_header); [MDN, Including credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#including_credentials).

## 4. FastAPI headers belong on the actual returned Response

The injected Response parameter is temporary. FastAPI extracts its headers when it constructs a response from ordinary returned data, such as a dict. Returning a separate JSONResponse follows a different path: FastAPI passes the returned Response directly and does not change it. Therefore headers set only on the injected object do not automatically appear on that separate response.

Use either ordinary data with the injected Response, or set headers on the JSONResponse that is returned:

```python
return JSONResponse(content={"ok": True}, headers={"X-Example": "value"})
```

Sources: [FastAPI, Response Headers: temporary Response and direct response examples](https://fastapi.tiangolo.com/advanced/response-headers/); [FastAPI, Return a Response Directly: passes returned Response directly without changes](https://fastapi.tiangolo.com/advanced/response-directly/#return-a-response); [Starlette, Response constructor accepts headers](https://starlette.dev/responses/#response).

## 5. Flask default sessions are signed client-side cookies

Flask's default SecureCookieSessionInterface stores session data in signed cookies through itsdangerous. The signature detects unauthorized modification; it does not encrypt the contents. Flask explicitly says the user can inspect cookie contents, while forging a valid modification requires the signing secret. A server-side session store requires a different session implementation; it is not Flask's default.

Sources: [Flask API, SecureCookieSessionInterface](https://flask.palletsprojects.com/en/stable/api/#flask.sessions.SecureCookieSessionInterface); [Flask Quickstart, Sessions](https://flask.palletsprojects.com/en/stable/quickstart/#sessions).
