(function () {
  const $ = (id) => document.getElementById(id);

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return d.toLocaleString("zh-CN", { hour12: false });
    } catch {
      return iso;
    }
  }

  function setStatus(type, html) {
    const el = $("status");
    el.classList.remove("hidden", "ok", "err", "warn", "loading");
    if (type === "ok") el.classList.add("ok");
    else if (type === "err") el.classList.add("err");
    else if (type === "warn") el.classList.add("warn");
    else if (type === "loading") el.classList.add("loading");
    el.innerHTML = html;
    el.classList.remove("hidden");
  }

  function hideStatus() {
    $("status").classList.add("hidden");
  }

  function setFormBusy(busy) {
    const form = document.getElementById("form-match");
    if (form) form.setAttribute("aria-busy", busy ? "true" : "false");
    ["file-mapping", "file-sku"].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = busy;
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function jobRowHtml(j) {
    const id = j.id;
    const fc = j.fail_count ? `<span class="bad">${j.fail_count}</span>` : String(j.fail_count ?? 0);
    return `
        <tr>
          <td>${fmtTime(j.created_at)}</td>
          <td>${j.ok_count}</td>
          <td>${fc}</td>
          <td class="ellipsis" title="${escapeAttr(j.mapping_name)}">${escapeHtml(j.mapping_name)}</td>
          <td class="ellipsis" title="${escapeAttr(j.sku_name)}">${escapeHtml(j.sku_name)}</td>
          <td class="nowrap">
            <a class="btn link" href="/api/jobs/${id}/download">下载结果</a>
            ${
              j.fail_count
                ? `<button type="button" class="btn link" data-job-errors="${id}">失败明细</button>`
                : ""
            }
          </td>
        </tr>`;
  }

  function bindErrorButtons(scope) {
    scope.querySelectorAll("[data-job-errors]").forEach((btn) => {
      btn.addEventListener("click", () => openErrors(btn.getAttribute("data-job-errors")));
    });
  }

  function removePlaceholderRows(tbody) {
    tbody.querySelectorAll("tr").forEach((tr) => {
      const c = tr.cells[0];
      if (tr.cells.length === 1 && c && Number(c.colSpan) >= 6) tr.remove();
    });
  }

  /** 若列表里还没有本次任务（例如 GET 被缓存），用接口返回的数据插一行，保证立刻可见 */
  function ensureJobRowFromResponse(data) {
    const tbody = $("jobs-body");
    if (!tbody || !data.job_id) return;
    const sel = `a[href="/api/jobs/${data.job_id}/download"]`;
    if (tbody.querySelector(sel)) return;
    removePlaceholderRows(tbody);
    tbody.insertAdjacentHTML(
      "afterbegin",
      jobRowHtml({
        id: data.job_id,
        created_at: data.created_at,
        ok_count: data.ok_count,
        fail_count: data.fail_count,
        mapping_name: data.mapping_name,
        sku_name: data.sku_name,
      })
    );
    bindErrorButtons(tbody);
  }

  async function loadJobs() {
    const tbody = $("jobs-body");
    try {
      const r = await fetch(`/api/jobs?_=${Date.now()}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!r.ok) throw new Error("列表加载失败");
      const jobs = await r.json();
      if (!Array.isArray(jobs)) throw new Error("列表格式异常");
      if (!jobs.length) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="muted">暂无记录，完成一次匹配后会出现在这里</td></tr>';
        return;
      }
      tbody.innerHTML = jobs.map((j) => jobRowHtml(j)).join("");
      bindErrorButtons(tbody);
    } catch (e) {
      console.error("loadJobs", e);
      tbody.innerHTML = `<tr><td colspan="6" class="bad">加载失败，请刷新页面重试</td></tr>`;
    }
  }

  function scrollToJobs() {
    const el = document.getElementById("section-jobs");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function openErrors(jobId) {
    const panel = $("panel-errors");
    const list = $("errors-list");
    const title = $("panel-errors-title");
    title.textContent = "失败明细";
    list.innerHTML = '<li class="muted">加载中…</li>';
    panel.classList.remove("hidden");
    try {
      const r = await fetch(`/api/jobs/${jobId}/errors?_=${Date.now()}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!r.ok) throw new Error("加载失败");
      const data = await r.json();
      if (!data.errors || !data.errors.length) {
        list.innerHTML = '<li class="muted">没有失败记录</li>';
        return;
      }
      list.innerHTML = data.errors
        .map(
          (e) =>
            `<li><span class="row-idx">第 ${e.row_index} 行</span> ${escapeHtml(e.reason)}</li>`
        )
        .join("");
    } catch {
      list.innerHTML = '<li class="bad">加载失败，请稍后重试</li>';
    }
  }

  $("btn-close-errors").addEventListener("click", () => {
    $("panel-errors").classList.add("hidden");
  });

  $("form-match").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    hideStatus();
    const fm = $("file-mapping").files[0];
    const fs = $("file-sku").files[0];
    if (!fm || !fs) {
      setStatus("err", "请选择两个文件后再开始匹配。");
      return;
    }
    const btn = $("btn-run");
    const spin = $("btn-spinner");
    setFormBusy(true);
    btn.disabled = true;
    spin.classList.remove("hidden");
    setStatus(
      "loading",
      "<strong>正在匹配…</strong><br/>正在上传两个表格，服务器正在计算，请勿关闭页面。<br/><span class=\"subtle\">大文件可能需要十几秒，请稍候。</span>"
    );
    const body = new FormData();
    body.append("mapping", fm);
    body.append("sku", fs);
    try {
      const r = await fetch("/api/match", {
        method: "POST",
        body,
        cache: "no-store",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const msg = data.detail ?? data.message ?? r.statusText ?? "匹配失败";
        let text;
        if (Array.isArray(msg)) {
          text = msg.map((x) => (x && x.msg) || JSON.stringify(x)).join("；");
        } else if (msg && typeof msg === "object") {
          text = JSON.stringify(msg);
        } else {
          text = String(msg);
        }
        setStatus("err", `<strong>匹配未成功</strong><br/>${escapeHtml(text)}`);
        return;
      }
      let extra = "";
      if (data.map_warnings && data.map_warnings.length) {
        extra =
          "<br/><strong>提示（配对表）</strong><ul>" +
          data.map_warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("") +
          "</ul>";
      }
      setStatus(
        "ok",
        `<strong>匹配完成</strong>：成功 <strong>${data.ok_count}</strong> 条，失败 <strong>${data.fail_count}</strong> 条。<br/>
         <a class="btn link inline" href="${String(data.download_url || "#")}">下载本次结果表</a>${extra}`
      );
      await loadJobs();
      ensureJobRowFromResponse(data);
      requestAnimationFrame(() => scrollToJobs());
    } catch (e) {
      setStatus("err", `<strong>网络或服务器异常</strong><br/>${escapeHtml(e.message || String(e))}`);
    } finally {
      setFormBusy(false);
      btn.disabled = false;
      spin.classList.add("hidden");
    }
  });

  loadJobs();
})();
