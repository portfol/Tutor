// 여의도 인사이트 - 클라이언트 렌더링 스크립트
// data/market.json (GitHub Actions가 KRX 실시간 피드로부터 주기적으로 갱신)
// 을 fetch 하여 지수 보드와 핵심 스탯 카드를 업데이트한다.
(function () {
  "use strict";

  /** Fallback (JSON 로드 실패 시에만 사용) */
  const FALLBACK_INDICES = [
    { name: "KOSPI",      price: "—", chg: "—", dir: "" },
    { name: "KOSDAQ",     price: "—", chg: "—", dir: "" },
    { name: "KOSPI 200",  price: "—", chg: "—", dir: "" },
    { name: "USD/KRW",    price: "—", chg: "—", dir: "" },
  ];

  /* ---------- 포매터 ---------- */
  const fmtPrice = (v, digits = 2) =>
    v.toLocaleString("ko-KR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });

  const fmtSigned = (v, digits = 2) =>
    (v >= 0 ? "+" : "") +
    v.toLocaleString("ko-KR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });

  /* ---------- 렌더 ---------- */
  function renderBoard(items) {
    const list = document.getElementById("index-list");
    if (!list) return;
    list.innerHTML = items
      .map(
        (i) => `
        <li>
          <span class="name">${i.name}</span>
          <span>
            <span class="price">${i.price}</span>
            <span class="chg ${i.dir}">${i.chg}</span>
          </span>
        </li>`
      )
      .join("");
  }

  function updateStatCard(labelText, value, dir, sub) {
    document.querySelectorAll(".stat-card").forEach((card) => {
      const label = card.querySelector(".stat-label");
      if (!label || label.textContent.trim() !== labelText) return;
      const val = card.querySelector(".stat-value");
      const s = card.querySelector(".stat-sub");
      if (val) {
        val.textContent = value;
        val.classList.remove("up", "down");
        if (dir) val.classList.add(dir);
      }
      if (s && sub !== undefined) s.textContent = sub;
    });
  }

  /* ---------- KRX JSON 적용 ---------- */
  function applyMarketData(data) {
    if (!data) return;

    const board = [];

    (data.indices || []).forEach((i) => {
      if (typeof i.close !== "number") return;
      const dir = (i.change || 0) >= 0 ? "up" : "down";
      board.push({
        name: i.name,
        price: fmtPrice(i.close),
        chg: `${fmtSigned(i.change || 0)} (${fmtSigned(i.changePct || 0)}%)`,
        dir,
      });
    });

    (data.fx || []).forEach((f) => {
      if (typeof f.close !== "number") return;
      const dir = (f.change || 0) >= 0 ? "up" : "down";
      board.push({
        name: f.name,
        price: fmtPrice(f.close),
        chg: `${fmtSigned(f.change || 0)} (${fmtSigned(f.changePct || 0)}%)`,
        dir,
      });
    });

    if (board.length) renderBoard(board);

    // 스탯 카드 업데이트
    const kospi = (data.indices || []).find((i) => i.name === "KOSPI");
    if (kospi) {
      const wk = kospi.week && typeof kospi.week.changePct === "number"
        ? kospi.week.changePct
        : kospi.changePct;
      updateStatCard(
        "KOSPI 주간 등락",
        `${fmtSigned(wk)}%`,
        (wk || 0) >= 0 ? "up" : "down",
        `종가 ${fmtPrice(kospi.close)} · ${kospi.date || ""}`
      );
    }

    const usdkrw = (data.fx || []).find((f) => f.name === "USD/KRW");
    if (usdkrw && typeof usdkrw.close === "number") {
      const wk = usdkrw.week && typeof usdkrw.week.changePct === "number"
        ? usdkrw.week.changePct
        : null;
      const subPieces = [
        `전일비 ${fmtSigned(usdkrw.change || 0)} (${fmtSigned(usdkrw.changePct || 0)}%)`,
      ];
      if (wk !== null) subPieces.push(`주간 ${fmtSigned(wk)}%`);
      updateStatCard(
        "원/달러 환율",
        fmtPrice(usdkrw.close),
        usdkrw.change >= 0 ? "down" : "up", // 환율 하락 = 원화 강세 (녹색)
        subPieces.join(" · ")
      );
    }

    // 외국인 순매수 (KOSPI dealTrend, 단위: 억원)
    if (kospi && kospi.dealTrend && typeof kospi.dealTrend.foreign === "number") {
      const eok = kospi.dealTrend.foreign;         // 억원
      const jo = eok / 10000;                       // 조원
      const absJo = Math.abs(jo);
      const display =
        absJo >= 1
          ? `${fmtSigned(jo, 2)}조`
          : `${fmtSigned(eok, 0)}억`;
      const biz = (kospi.dealTrend.bizdate || "").replace(
        /^(\d{4})(\d{2})(\d{2})$/,
        "$1-$2-$3"
      );
      updateStatCard(
        "외국인 순매수",
        display,
        eok >= 0 ? "up" : "down",
        `KOSPI · ${biz || kospi.date || ""}`
      );
    }

    // 헤더/푸터 날짜를 데이터 기준일로 갱신
    const baseDate =
      (kospi && kospi.date) ||
      (usdkrw && usdkrw.date) ||
      (data.updatedAt && data.updatedAt.slice(0, 10));
    if (baseDate) {
      const rd = document.getElementById("report-date");
      const fd = document.getElementById("footer-date");
      if (rd) rd.textContent = baseDate;
      if (fd) fd.textContent = baseDate;
    }

    // 데이터 소스 배지
    const src = document.getElementById("data-source");
    if (src) {
      const ts = data.updatedAt ? data.updatedAt.replace("T", " ").slice(0, 16) : "";
      src.textContent = `데이터 최종 갱신: ${ts} KST`;
      src.title = data.source || "";
    }
  }

  /* ---------- 부팅 ---------- */

  // 1) 즉시 자리표시 렌더 (JSON 늦게 도착해도 레이아웃 유지)
  renderBoard(FALLBACK_INDICES);

  // 2) 오늘 날짜(브라우저 기준) 임시 표기
  const today = new Date();
  const dateStr = today.toISOString().slice(0, 10);
  const rd0 = document.getElementById("report-date");
  const fd0 = document.getElementById("footer-date");
  if (rd0) rd0.textContent = dateStr;
  if (fd0) fd0.textContent = dateStr;

  // 3) KRX 스냅샷 로드
  fetch("data/market.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      if (d) applyMarketData(d);
    })
    .catch((err) => {
      console.warn("[market.json] load failed", err);
    });

  // 4) 섹션 스무스 스크롤
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href");
      if (id && id.length > 1) {
        const t = document.querySelector(id);
        if (t) {
          e.preventDefault();
          t.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });
})();
