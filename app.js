// 여의도 인사이트 - 클라이언트 렌더링 스크립트
(function () {
  "use strict";

  const indices = [
    { name: "KOSPI",     price: "2,742.18", chg: "+47.21 (+1.75%)", dir: "up" },
    { name: "KOSDAQ",    price: "  868.34", chg: "+12.04 (+1.41%)", dir: "up" },
    { name: "S&P 500",   price: "5,248.49", chg: "+22.10 (+0.42%)", dir: "up" },
    { name: "NASDAQ",    price: "16,441.2", chg: "+85.63 (+0.52%)", dir: "up" },
    { name: "상해종합",   price: "3,078.11", chg: " -9.80 (-0.32%)", dir: "down" },
    { name: "WTI ($/bbl)", price: "   85.24", chg: "+1.12 (+1.33%)", dir: "up" },
    { name: "USD/KRW",   price: "1,342.50", chg: " -4.20 (-0.31%)", dir: "down" }
  ];

  const list = document.getElementById("index-list");
  if (list) {
    list.innerHTML = indices
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

  // 오늘 날짜 자동 표기 (KST 기준)
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  const dateStr = `${y}-${m}-${d}`;
  const rd = document.getElementById("report-date");
  const fd = document.getElementById("footer-date");
  if (rd) rd.textContent = dateStr;
  if (fd) fd.textContent = dateStr;

  // 섹션 스무스 스크롤
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href");
      if (id && id.length > 1) {
        const target = document.querySelector(id);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });
})();
