# Raw Replay Binding — donor notice

Conceptual donor consulted:

- Repository: `Seyamalam/Kaggriculture`
- File: `scripts/replay_trace_gate.py`
- Related attribution file: `scripts/replay_loss_attribution.py`
- License: MIT
- Copyright: (c) 2026 Touhidul Alam Seyam

The donor was used to cross-check two semantic facts: (1) replay state `i`
stores the action applied to the preceding observation/state, and (2) replaying
a recorded opponent action schedule after a candidate diverges is an open-loop
historical stress test, not an adaptive reconstruction or ladder-win estimate.
The TITAN V4 binder is independently written, dependency-free, and does not
copy the donor's engine-execution harness.

MIT License

Copyright (c) 2026 Touhidul Alam Seyam

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
