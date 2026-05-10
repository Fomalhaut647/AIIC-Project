"""Plan3 web DOM contract test — Spec E §10 / §7.4."""
import re
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"


def test_index_html_has_mic_toggle():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="toggle-mic"' in html


def test_index_html_has_speaker_toggle():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="toggle-speaker"' in html


def test_index_html_has_upload_button():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="upload-btn"' in html
    assert 'id="upload-input"' in html


def test_index_html_has_mic_buttons_for_three_textareas():
    """三个 mic 按钮：onboarding chat / interview answer / resume_iterate textarea 各一。"""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    mic_btns = html.count('class="mic-btn"')
    assert mic_btns >= 3, f"expected >= 3 mic buttons, found {mic_btns}"


def test_styles_has_mic_pulse_class():
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    assert ".mic-pulse" in css


# ============================================================
# Plan3.6 layout fix — 3-col grid + cheat-panel inline (no overlay)
# ============================================================


def test_styles_view_interview_three_col_grid():
    """Plan3.6: .interview-layout 是 3-col grid (sidebar | main | cheat-panel)。"""
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    # 找 .interview-layout { ... grid-template-columns: ...; ... }
    m = re.search(r"\.interview-layout\s*\{[^}]*grid-template-columns:\s*([^;]+);", css, re.DOTALL)
    assert m, "no grid-template-columns rule on .interview-layout"
    cols = m.group(1)
    # 3-col: 至少 3 个 minmax(...) 或 fr 单位 token
    minmax_count = cols.count("minmax(")
    assert minmax_count >= 3, f"expected >=3 minmax() in grid-template-columns, got {minmax_count}: {cols!r}"


def test_styles_cheat_panel_not_fixed():
    """Plan3.6: .cheat-panel 不再 position: fixed (改为 inline grid column + sticky)。"""
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    # 找 .cheat-panel { ... } 主规则块 (非 .cheat-panel.hidden 等子规则)
    m = re.search(r"\.cheat-panel\s*\{([^}]+)\}", css, re.DOTALL)
    assert m, ".cheat-panel rule not found"
    body = m.group(1)
    assert "position: fixed" not in body and "position:fixed" not in body, \
        f".cheat-panel still has position: fixed (Bug B 未修): {body!r}"


def test_styles_cheat_panel_no_drawer_tab_class():
    """Plan3.6: .cheat-drawer-tab class 已弃用 (toggle 改为 sidebar inline button)。"""
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    assert ".cheat-drawer-tab" not in css, "drawer-tab class still in CSS — should be removed in Plan3.6"


def test_index_html_cheat_panel_inside_layout():
    """Plan3.6: #cheat-panel 在 .interview-layout 内 (作为 grid 第 3 列)。

    用 substring offset 校验比 regex match 严格：
    cheat-panel 出现位置必须在 .interview-layout 开标签之后、且在 </section> 之前
    (即 view-interview 的 section 关闭之前)，并且 cheat-panel 后面应该紧跟着
    layout 的 </div> 然后才是 </section>，证明它真的在 layout 内部最末尾。
    """
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    layout_open = html.find('class="interview-layout"')
    assert layout_open > -1, ".interview-layout block not found"
    cheat_pos = html.find('id="cheat-panel"', layout_open)
    assert cheat_pos > -1, "#cheat-panel not found after .interview-layout"
    # 找 layout_open 之后第一个 </section> 关闭 (= view-interview 末尾)
    section_close = html.find('</section>', layout_open)
    assert section_close > -1, "view-interview </section> not found"
    assert cheat_pos < section_close, \
        "#cheat-panel found but not before view-interview </section>"
    # cheat-panel 应该在 .interview-layout 的 closing div 之前
    # 找 cheat-panel 之后第一个 </div>，再确认 </div> 在 section_close 之前
    div_close_after_cheat = html.find('</div>', cheat_pos)
    assert div_close_after_cheat > -1 and div_close_after_cheat < section_close, \
        "#cheat-panel must be inside .interview-layout div (Plan3.6 grid 3rd col), " \
        "expected </div> after #cheat-panel before </section>"


def test_index_html_cheat_toggle_inside_sidebar():
    """Plan3.6: #btn-cheat-toggle 在 .interview-sidebar 内 (替代 fixed drawer tab)。"""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<aside\s+class="interview-sidebar"[^>]*>(.*?)</aside>',
                  html, re.DOTALL)
    assert m, ".interview-sidebar block not found"
    sidebar_inner = m.group(1)
    assert 'id="btn-cheat-toggle"' in sidebar_inner, \
        "#btn-cheat-toggle must be inside .interview-sidebar (Plan3.6 inline button)"
