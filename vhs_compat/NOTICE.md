# Vendored VideoHelperSuite code

`vhs_compat` is a source copy of the VideoHelperSuite Python implementation,
adapted only to let `Video Combine 🎥🅥🅗🅢 V2` run without a separate
VideoHelperSuite installation.  Its original project is:

https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite

The copied code is distributed under GNU GPL v3.0.  See `LICENSE` in this
directory and the toolbox root license.

Changes made by FeiHou Toolbox: the vendored preview endpoints use the private
`/feihou-vhs/` prefix, preventing conflicts when VideoHelperSuite is also
installed.
