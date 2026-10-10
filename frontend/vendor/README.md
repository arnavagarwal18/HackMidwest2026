# Vendored third-party code

| File | What | Source | License |
| --- | --- | --- | --- |
| `qrcode.js` | QR code generator (draws the tone page QR on `#/calibrate`) | [kazuhikoarase/qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator), `js/dist/qrcode.js` at commit `83b7e8fe3fddd3b0368dbafd6ce56995bd25e3c8`, unmodified | MIT, see `LICENSE-qrcode-generator.txt` (the file's own header carries it too) |

`index.html` loads it with a classic `<script>` tag, which defines the global `qrcode`; `js/calibrate/qr.js` is the only user.
