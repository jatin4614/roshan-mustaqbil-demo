/* Roshan Mustaqbil screens: tiny behaviour layer.
 *
 * Everything is delegated from `document`, so it keeps working after the
 * sidebar swaps page content in with htmx. Guarded so a second include of
 * this file is a no-op.
 */
(function () {
    if (window.rmUI) return;
    window.rmUI = true;

    /* ── Tooltip: any element with data-tip (optional data-tip-title) ── */
    var tip = null;
    function ensureTip() {
        if (!tip) {
            tip = document.createElement("div");
            tip.className = "rm-tip";
            tip.setAttribute("role", "tooltip");
            document.body.appendChild(tip);
        }
        return tip;
    }
    function showTip(target) {
        var el = ensureTip();
        var title = target.getAttribute("data-tip-title");
        el.textContent = "";
        if (title) {
            var b = document.createElement("b");
            b.textContent = title;
            el.appendChild(b);
        }
        el.appendChild(document.createTextNode(target.getAttribute("data-tip")));
        var box = target.getBoundingClientRect();
        var x = Math.min(Math.max(box.left + box.width / 2, 140), window.innerWidth - 140);
        el.style.left = x + "px";
        el.style.top = box.top + "px";
        el.classList.add("is-on");
    }
    function hideTip() { if (tip) tip.classList.remove("is-on"); }

    document.addEventListener("mouseover", function (event) {
        var target = event.target.closest && event.target.closest("[data-tip]");
        if (target) showTip(target); else hideTip();
    });
    document.addEventListener("focusin", function (event) {
        var target = event.target.closest && event.target.closest("[data-tip]");
        if (target) showTip(target);
    });
    document.addEventListener("focusout", hideTip);
    window.addEventListener("scroll", hideTip, true);

    /* ── Whole table rows open the student ────────────────────────────── */
    document.addEventListener("click", function (event) {
        if (event.target.closest("a, button, input, select, label, textarea, form")) return;
        var row = event.target.closest("[data-href]");
        if (row) window.location.href = row.getAttribute("data-href");
    });

    /* ── Filters: selects submit their form immediately ───────────────── */
    document.addEventListener("change", function (event) {
        var control = event.target;
        if (control.matches && control.matches("[data-autosubmit]")) {
            var form = control.form;
            if (form) {
                var page = form.querySelector("input[name=page]");
                if (page) page.remove();
                form.requestSubmit ? form.requestSubmit() : form.submit();
            }
        }
        var conditional = control.closest && control.closest("form[data-conditional]");
        if (conditional) syncConditional(conditional);
    });

    document.addEventListener("click", function (event) {
        var toggle = event.target.closest("[data-toggle-more]");
        if (!toggle) return;
        var panel = document.getElementById(toggle.getAttribute("data-toggle-more"));
        if (!panel) return;
        panel.hidden = !panel.hidden;
        toggle.setAttribute("aria-expanded", String(!panel.hidden));
    });

    /* ── Conditional fields ───────────────────────────────────────────
     * data-show-when="career_goal=Defence"            one rule
     * data-show-when="career_goal=UPSC|Other"         any of the values
     * data-show-when="career_goal=Other;exam=Other"   either rule
     */
    function fieldValues(form, name) {
        var values = [];
        form.querySelectorAll("[name='" + name + "']").forEach(function (control) {
            if ((control.type === "checkbox" || control.type === "radio") && !control.checked) return;
            values.push(control.value);
        });
        return values;
    }
    function syncConditional(form) {
        form.querySelectorAll("[data-show-when]").forEach(function (wrapper) {
            var visible = wrapper.getAttribute("data-show-when").split(";").some(function (rule) {
                var parts = rule.split("=");
                var wanted = parts.slice(1).join("=").split("|");
                return fieldValues(form, parts[0]).some(function (value) { return wanted.indexOf(value) !== -1; });
            });
            wrapper.hidden = !visible;
        });
    }

    /* ── Live areas (desk, call list): busy state and failures ────────── */
    function liveArea(elt) { return elt && elt.closest ? elt.closest("[data-live]") : null; }
    function showProblem(area, message, linkText, href) {
        var box = area.querySelector("[data-live-error]");
        if (!box) return;
        box.hidden = false;
        box.querySelector("span").textContent = message;
        var link = box.querySelector("a");
        if (link) {
            link.hidden = !href;
            if (href) { link.href = href; link.textContent = linkText; }
        }
    }
    document.addEventListener("htmx:beforeRequest", function (event) {
        var area = liveArea(event.detail.elt);
        if (!area) return;
        area.classList.add("is-busy");
        var box = area.querySelector("[data-live-error]");
        if (box) box.hidden = true;
    });
    document.addEventListener("htmx:afterRequest", function (event) {
        var area = liveArea(event.detail.elt);
        if (!area) return;
        area.classList.remove("is-busy");
        var xhr = event.detail.xhr;
        if (xhr && xhr.responseURL && new URL(xhr.responseURL).pathname.replace(/\/$/, "") === "/login") {
            showProblem(area, "You've been signed out, so this wasn't saved.", "Sign in again", "/login/?next=" + encodeURIComponent(location.pathname + location.search));
        }
    });
    ["htmx:responseError", "htmx:sendError", "htmx:timeout"].forEach(function (name) {
        document.addEventListener(name, function (event) {
            var area = liveArea(event.detail.elt);
            if (!area) return;
            area.classList.remove("is-busy");
            var offline = name !== "htmx:responseError";
            showProblem(area, offline ? "Not saved: the connection dropped. Check the internet and try again." : "Not saved: something went wrong on the server. Try again.", "", "");
        });
    });

    /* ── Desk: keep the search box ready; arrow keys move through results ─ */
    function deskButtons() {
        return Array.prototype.slice.call(document.querySelectorAll("#rm-desk-results button[type=submit]"));
    }
    document.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
        var inDesk = event.target.id === "rm-desk-search" || (event.target.closest && event.target.closest("#rm-desk-results"));
        if (!inDesk) return;
        var buttons = deskButtons();
        if (!buttons.length) return;
        var index = buttons.indexOf(event.target);
        var next = event.key === "ArrowDown" ? index + 1 : index - 1;
        event.preventDefault();
        if (next < 0) { document.getElementById("rm-desk-search").focus(); return; }
        buttons[Math.min(next, buttons.length - 1)].focus();
    });

    function initDesk(root) {
        var input = (root || document).querySelector("#rm-desk-search");
        if (input && !input.dataset.ready) {
            input.dataset.ready = "1";
            input.focus();
        }
    }

    function init(root) {
        (root || document).querySelectorAll("form[data-conditional]").forEach(syncConditional);
        // The visit calendar scrolls sideways on small screens: start at today.
        (root || document).querySelectorAll(".rm-cal").forEach(function (cal) { cal.scrollLeft = cal.scrollWidth; });
        initDesk(root);
    }

    document.addEventListener("DOMContentLoaded", function () { init(document); });
    document.addEventListener("htmx:afterSettle", function (event) {
        init(document);
        var source = event.detail && event.detail.requestConfig && event.detail.requestConfig.elt;
        if (!source || !source.closest) return;
        // After marking someone present, clear the box for the next student.
        var flash = document.getElementById("rm-desk-flash");
        if (flash && source.closest("[data-desk]") && flash.dataset.clear === "1") {
            var input = document.getElementById("rm-desk-search");
            if (input) { input.value = ""; input.focus(); }
        }
        // Call list: after saving, move straight on to the next student.
        var saved = document.querySelector("[data-call-saved]:not([data-seen])");
        if (saved) {
            saved.setAttribute("data-seen", "1");
            var next = saved.nextElementSibling;
            var select = next && next.querySelector("select");
            if (select) select.focus();
        }
    });
    if (document.readyState !== "loading") init(document);
})();
