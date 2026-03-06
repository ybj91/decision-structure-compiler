"""Generate an animated GIF that simulates the DSC demo CLI output."""

from PIL import Image, ImageDraw, ImageFont
import os

# Terminal dimensions
WIDTH = 860
LINE_H = 18
PAD_X = 16
PAD_TOP = 44
WINDOW_BAR_H = 36

# Colors (GitHub dark theme)
BG = (13, 17, 23)
BAR_BG = (22, 27, 34)
WHITE = (201, 209, 217)
GREEN = (126, 231, 135)
BLUE = (88, 166, 255)
AMBER = (255, 159, 67)
GRAY = (106, 115, 125)
DIM = (72, 79, 88)
RED_DOT = (255, 95, 87)
YELLOW_DOT = (254, 188, 46)
GREEN_DOT = (40, 200, 64)

# Try to find a monospace font
FONT_SIZE = 13
FONT = None
font_paths = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "C:/Windows/Fonts/lucon.ttf",
]
for fp in font_paths:
    if os.path.exists(fp):
        FONT = ImageFont.truetype(fp, FONT_SIZE)
        break
if FONT is None:
    FONT = ImageFont.load_default()

FONT_BOLD = None
bold_paths = [
    "C:/Windows/Fonts/consolab.ttf",
    "C:/Windows/Fonts/courbd.ttf",
]
for fp in bold_paths:
    if os.path.exists(fp):
        FONT_BOLD = ImageFont.truetype(fp, FONT_SIZE)
        break
if FONT_BOLD is None:
    FONT_BOLD = FONT

# Each frame is a list of (text, color, bold) lines to show
# We'll build up lines and create frames at certain points

lines = []

def add(text, color=WHITE, bold=False, delay=1):
    """Add a line, return list of (lines_snapshot, frame_count)."""
    lines.append((text, color, bold))
    return delay

# Build the sequence with delays (in frames, ~100ms each)
frames_spec = []  # list of (delay_frames,)

frames_spec.append(add("$ python examples/full_pipeline/demo.py", GREEN, bold=True, delay=8))
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("══════════════════════════════════════════════════════════", GRAY, delay=1))
frames_spec.append(add("  DECISION STRUCTURE COMPILER — Full Pipeline Demo", WHITE, bold=True, delay=1))
frames_spec.append(add("══════════════════════════════════════════════════════════", GRAY, delay=6))

frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("--- STEP 2: LLM simulates execution traces ---", BLUE, bold=True, delay=6))
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  Trace 1: account (low) → 2 steps", AMBER, delay=3))
frames_spec.append(add("    triage → [initiate_password_reset] → awaiting_confirmation", DIM, delay=2))
frames_spec.append(add("    awaiting_confirmation → [close_ticket] → resolved", DIM, delay=4))
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  Trace 2: billing (medium) → 3 steps", AMBER, delay=3))
frames_spec.append(add("    triage → [lookup_billing_history] → billing_review", DIM, delay=2))
frames_spec.append(add("    billing_review → [process_refund] → refund_issued", DIM, delay=2))
frames_spec.append(add("    refund_issued → [close_ticket] → resolved", DIM, delay=4))
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  Trace 3: technical (critical) → 3 steps", AMBER, delay=3))
frames_spec.append(add("    triage → [check_system_status] → incident_detected", DIM, delay=2))
frames_spec.append(add("    incident_detected → [notify_known_incident] → monitoring", DIM, delay=2))
frames_spec.append(add("    monitoring → [close_ticket] → resolved", DIM, delay=6))

frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("--- STEP 4: LLM extracts decision graph ---", BLUE, bold=True, delay=4))
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  Phase A — Raw extraction:         8 LLM calls total", GRAY, delay=3))
frames_spec.append(add("  Phase B — State normalization:    7 canonical states", GRAY, delay=3))
frames_spec.append(add("  Phase C — Condition formalization: 15 transitions", GRAY, delay=8))

frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("--- STEP 7: Execute at runtime (NO LLM CALLS) ---", GREEN, bold=True, delay=8))

# Test 1
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  PASSWORD RESET — account issue", WHITE, bold=True, delay=3))
frames_spec.append(add("    [triage] + {issue_type=account, severity=low}", DIM, delay=2))
frames_spec.append(add("      → initiate_password_reset → [awaiting_confirmation]", GREEN, delay=3))
frames_spec.append(add("    [awaiting_confirmation] + {reset_completed=True}", DIM, delay=2))
frames_spec.append(add("      → close_ticket → [resolved]", GREEN, delay=2))
frames_spec.append(add("    Result: RESOLVED in 2 steps", GREEN, bold=True, delay=8))

# Test 2
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  BILLING REFUND — duplicate charge under $100", WHITE, bold=True, delay=3))
frames_spec.append(add("    [triage] + {issue_type=billing}", DIM, delay=2))
frames_spec.append(add("      → lookup_billing_history → [billing_review]", GREEN, delay=2))
frames_spec.append(add("    [billing_review] + {duplicate=True, amount=29.99}", DIM, delay=2))
frames_spec.append(add("      → process_refund → [refund_issued]", GREEN, delay=2))
frames_spec.append(add("    [refund_issued] + {customer_satisfied=True}", DIM, delay=2))
frames_spec.append(add("      → close_ticket → [resolved]", GREEN, delay=2))
frames_spec.append(add("    Result: RESOLVED in 3 steps", GREEN, bold=True, delay=8))

# Test 3
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("  UNKNOWN ISSUE — falls through to human", WHITE, bold=True, delay=3))
frames_spec.append(add("    [triage] + {issue_type=shipping, severity=low}", DIM, delay=2))
frames_spec.append(add("      → escalate_to_human → [resolved]", AMBER, delay=2))
frames_spec.append(add("    Result: RESOLVED in 1 step (fallback)", AMBER, bold=True, delay=10))

# Summary
frames_spec.append(add("", WHITE, delay=1))
frames_spec.append(add("══════════════════════════════════════════════════════════", GRAY, delay=1))
frames_spec.append(add("  SUMMARY", WHITE, bold=True, delay=3))
frames_spec.append(add("══════════════════════════════════════════════════════════", GRAY, delay=2))
frames_spec.append(add("  Compile time:  8 LLM calls → 7 states, 15 transitions", BLUE, delay=4))
frames_spec.append(add("  Runtime:       5 scenarios, 0 LLM calls, <1ms/step", GREEN, delay=4))
frames_spec.append(add("  Every decision: deterministic, auditable, traceable", WHITE, delay=20))


def render_frame(visible_lines, show_cursor=True):
    """Render current visible lines into an image."""
    # Calculate needed height
    n = len(visible_lines)
    h = WINDOW_BAR_H + PAD_TOP + max(n * LINE_H, LINE_H) + 20

    # But keep a fixed height for consistent GIF
    h = max(h, 580)
    h = 580  # fixed

    # Scroll if too many lines
    max_visible = (h - WINDOW_BAR_H - PAD_TOP - 10) // LINE_H
    if n > max_visible:
        visible_lines = visible_lines[n - max_visible:]

    img = Image.new("RGB", (WIDTH, h), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([(0, 0), (WIDTH, WINDOW_BAR_H)], fill=BAR_BG)
    # Window dots
    draw.ellipse([(14, 12), (26, 24)], fill=RED_DOT)
    draw.ellipse([(34, 12), (46, 24)], fill=YELLOW_DOT)
    draw.ellipse([(54, 12), (66, 24)], fill=GREEN_DOT)
    # Title text
    title = "Terminal — DSC Full Pipeline Demo"
    draw.text((WIDTH // 2 - len(title) * 3.5, 12), title, fill=GRAY, font=FONT)

    # Lines
    y = WINDOW_BAR_H + 14
    for text, color, bold in visible_lines:
        f = FONT_BOLD if bold else FONT
        draw.text((PAD_X, y), text, fill=color, font=f)
        y += LINE_H

    # Cursor
    if show_cursor:
        draw.rectangle([(PAD_X, y + 2), (PAD_X + 8, y + LINE_H - 2)], fill=WHITE)

    return img


# Generate frames
print("Generating frames...")
gif_frames = []
durations = []

for i, delay in enumerate(frames_spec):
    visible = lines[:i + 1]
    img = render_frame(visible, show_cursor=True)
    gif_frames.append(img)
    durations.append(delay * 100)  # ms

# Add a few extra frames at the end with cursor blink
for blink in range(6):
    img = render_frame(lines, show_cursor=(blink % 2 == 0))
    gif_frames.append(img)
    durations.append(500)

# Add a long pause then restart
img = render_frame(lines, show_cursor=False)
gif_frames.append(img)
durations.append(2000)

# Save GIF
output = os.path.join(os.path.dirname(__file__), "demo.gif")
print(f"Saving GIF to {output}...")
gif_frames[0].save(
    output,
    save_all=True,
    append_images=gif_frames[1:],
    duration=durations,
    loop=0,
    optimize=True,
)
print(f"Done! {len(gif_frames)} frames, {os.path.getsize(output) / 1024:.0f} KB")
