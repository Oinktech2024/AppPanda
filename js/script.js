// 開啟或關閉側邊欄
function toggleNav() {
    const sidebar = document.querySelector('.sidebar');
    const content = document.querySelector('.content');
    if (sidebar.style.left === "0px") {
        sidebar.style.left = "-300px";
        content.style.marginLeft = "0";
    } else {
        sidebar.style.left = "0";
        content.style.marginLeft = "300px";
    }
}

// 關閉側邊欄
function closeNav() {
    const sidebar = document.querySelector('.sidebar');
    const content = document.querySelector('.content');
    sidebar.style.left = "-300px";
    content.style.marginLeft = "0";
}

// 點擊側邊欄外部關閉側邊欄
window.addEventListener("click", function(event) {
    const sidebar = document.querySelector('.sidebar');
    const hamburgerMenu = document.querySelector('.hamburger-menu');
    if (event.target !== sidebar && event.target !== hamburgerMenu && !sidebar.contains(event.target)) {
        closeNav();
    }
});


// 當頁面加載時執行
window.addEventListener('DOMContentLoaded', () => {
    const nav = document.querySelector('nav');
    const content = document.querySelector('.content');

    // 獲取導航列的高度，並將其設置為 .content 的 margin-top
    if (nav && content) {
        const navHeight = nav.offsetHeight;
        content.style.marginTop = `${navHeight}px`;
    }
});

// 當窗口大小調整時重新計算高度
window.addEventListener('resize', () => {
    const nav = document.querySelector('nav');
    const content = document.querySelector('.content');

    if (nav && content) {
        const navHeight = nav.offsetHeight;
        content.style.marginTop = `${navHeight}px`;
    }
});


// 監聽所有漢堡菜單點擊
document.querySelector(".hamburger-menu").addEventListener("click", function() {
    showFireworks();
});

// 監聽所有的鏈接
document.querySelectorAll("a").forEach(function(link) {
    link.addEventListener("click", function() {
        showFireworks();
    });
});

var script = document.createElement('script');
script.type = 'text/javascript';
script.src = 'js/language.js'; 
document.head.appendChild(script);

function closeFlash() {
    const flash = document.querySelector('.flash-container');
    flash.classList.remove('show');
    flash.classList.add('hide');
    setTimeout(() => flash.remove(), 500); // 延遲後移除元素
}
