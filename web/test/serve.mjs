// serve.mjs DIR - serves DIR on 127.0.0.1 (a free port) and prints "http://127.0.0.1:PORT/". GET and HEAD only; a path
// that leaves DIR is 403. Imported, startServer(dir) resolves to {url, close, stats}.
import { createServer } from 'node:http';
import { readFile, stat, realpath } from 'node:fs/promises';
import { join, resolve, sep, extname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';

const TYPES = {
	'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
	'.css': 'text/css; charset=utf-8', '.json': 'application/json', '.wasm': 'application/wasm',
	'.svf': 'application/octet-stream', '.txt': 'text/plain; charset=utf-8', '.png': 'image/png',
};

// opts.gzip: URL paths sent gzip-encoded (Content-Encoding: gzip, Content-Length the compressed size); opts.redirect:
// {request URL (path and query): location} answered with a 302; opts.short: URL paths sent with a Content-Length larger
// than the body, the connection closed after the body (a truncated response); opts.chunked: URL paths sent without a
// Content-Length (chunked); the body is written paced (16 KiB per 5 ms, each write awaiting drain) so that a client that
// cancels leaves most of it unwritten; opts.big: {URL path: {bytes, declared}} answers with a zero-filled body of that many
// bytes, with a Content-Length when declared and chunked otherwise, paced in both; opts.status: {URL path: code} answers
// that status with an empty body. Every other answer carries its Content-Length. stats() -> {URL path: {written, completed, closed[, error]}}
// for the paced bodies: the bytes handed to the socket, whether the whole body was sent (a HEAD: the response ended), whether the client left before
// that (closed), and the message of a server write error (error, absent when there was none; the connection is then also closed).
export async function startServer(dir, opts = {}) {
	const root = await realpath(resolve(dir));
	const stats = {};
	const paced = async (res, path, size, head) => { // size bytes of zeros (a body to write: the caller gives a Buffer for a file)
		const st = stats[path] = { written: 0, completed: false, closed: false };
		res.on('close', () => { if (!st.completed) st.closed = true; });
		if (head) return new Promise(ok => res.end(() => { st.completed = true; ok(); }));
		const body = Buffer.isBuffer(size) ? size : Buffer.alloc(size);
		try {
			for (let o = 0; o < body.length && !st.closed; o += 16384) {
				const part = body.subarray(o, o + 16384);
				const flushed = res.write(part);
				if (!st.closed) st.written += part.length; // counted as soon as the write is accepted, not after the drain
				if (!flushed) {
					await new Promise(ok => { const done = () => { res.off('drain', done); res.off('close', done); ok(); }; res.on('drain', done); res.on('close', done); });
				}
				if (st.closed) break;
				await new Promise(ok => setTimeout(ok, 5));
			}
			if (!st.closed) await new Promise(ok => res.end(() => { st.completed = true; ok(); }));
		} catch (err) { // a write that threw. Assumption: when the client leaves, 'close' fires first (closed is already set), so what is left here is the server's
			if (!st.closed) st.error = String(err?.message ?? err);
			if (!st.completed) st.closed = true; // either way the connection is over: stats() shows closed (the client left) or completed, and error besides
		}
	};
	const server = createServer(async (req, res) => {
		const send = (code, body, type = 'text/plain; charset=utf-8') => { res.writeHead(code, { 'content-type': type, 'content-length': Buffer.byteLength(body), 'cache-control': 'no-store' }); res.end(req.method === 'HEAD' ? undefined : body); };
		try {
			if (req.method !== 'GET' && req.method !== 'HEAD') return send(405, 'method not allowed');
			let path;
			try { path = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch { return send(400, 'bad path'); }
			if (path.includes('\0')) return send(400, 'bad path');
			if (Object.hasOwn(opts.redirect ?? {}, req.url)) { res.writeHead(302, { location: opts.redirect[req.url], 'cache-control': 'no-store' }); return res.end(); }
			if (Object.hasOwn(opts.status ?? {}, path)) return send(opts.status[path], '');
			if (Object.hasOwn(opts.big ?? {}, path)) {
				const { bytes, declared } = opts.big[path], headers = { 'content-type': 'application/octet-stream', 'cache-control': 'no-store' };
				if (declared) headers['content-length'] = bytes;
				res.writeHead(200, headers);
				return paced(res, path, bytes, req.method === 'HEAD'); // zeros are allocated only for a GET
			}
			if (path.endsWith('/')) path += 'index.html';
			const file = resolve(join(root, path));
			if (file !== root && !file.startsWith(root + sep)) return send(403, 'forbidden');
			const real = await realpath(file).catch(() => null);
			if (!real) return send(404, 'not found');
			if (real !== root && !real.startsWith(root + sep)) return send(403, 'forbidden');
			if (!(await stat(real)).isFile()) return send(404, 'not found');
			const body = await readFile(real), type = TYPES[extname(real).toLowerCase()] ?? 'application/octet-stream';
			if (opts.gzip?.includes(path)) {
				const gz = gzipSync(body);
				res.writeHead(200, { 'content-type': type, 'content-encoding': 'gzip', 'content-length': gz.length, 'cache-control': 'no-store' });
				return res.end(req.method === 'HEAD' ? undefined : gz);
			}
			if (opts.chunked?.includes(path)) {
				res.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' });
				return paced(res, path, body, req.method === 'HEAD');
			}
			if (opts.short?.includes(path)) {
				res.writeHead(200, { 'content-type': type, 'content-length': body.length + 1000, connection: 'close', 'cache-control': 'no-store' });
				return res.end(req.method === 'HEAD' ? undefined : body);
			}
			send(200, body, type);
		} catch (err) {
			send(500, String(err.message ?? err));
		}
	});
	await new Promise((ok, bad) => { server.once('error', bad); server.listen(0, '127.0.0.1', ok); });
	return { url: `http://127.0.0.1:${server.address().port}/`, close: () => new Promise(ok => server.close(ok)), stats: () => JSON.parse(JSON.stringify(stats)) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
	if (!process.argv[2]) { process.stderr.write('usage: serve.mjs DIR\n'); process.exit(2); }
	const { url } = await startServer(process.argv[2]);
	process.stdout.write(url + '\n');
}
