/* ===== AI旅游智能助手 前端逻辑 =====
 * 功能：会话管理（localStorage持久化） + SSE流式接收 + Markdown实时渲染
 */

const chatBox = document.getElementById('chatBox');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const convList = document.getElementById('convList');

const API_URL = '/chat/stream';
const STORE_KEY = 'travel_conversations_v1';

let conversations = loadConversations();   // [{id, title, messages:[{role, content}]}]
let currentConvId = null;
let sending = false;

/* ---------------- 会话存储 ---------------- */

function loadConversations() {
    try {
        return JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
    } catch (e) { return []; }
}

function saveConversations() {
    localStorage.setItem(STORE_KEY, JSON.stringify(conversations.slice(0, 50)));
}

function currentConv() {
    return conversations.find(c => c.id === currentConvId) || null;
}

/* ---------------- 侧边栏渲染 ---------------- */

function renderConvList() {
    convList.innerHTML = '';
    conversations.forEach(conv => {
        const btn = document.createElement('button');
        btn.className = 'conv-item' + (conv.id === currentConvId ? ' active' : '');
        btn.textContent = conv.title;
        btn.title = conv.title;
        btn.onclick = () => openConversation(conv.id);
        convList.appendChild(btn);
    });
}

function openConversation(id) {
    if (sending) return;
    currentConvId = id;
    chatBox.innerHTML = '';
    const conv = currentConv();
    if (conv) {
        conv.messages.forEach(m => {
            if (m.role === 'user') addMessage(m.content, true);
            else addMessage(m.content, false, true);
        });
    } else {
        renderWelcome();
    }
    renderConvList();
    scrollToBottom();
}

function newConversation() {
    if (sending) return;
    currentConvId = null;
    chatBox.innerHTML = '';
    renderWelcome();
    renderConvList();
    userInput.focus();
}

newChatBtn.onclick = newConversation;

/* ---------------- 欢迎卡片（示例问题可点击发送） ---------------- */

const WELCOME_ITEMS = [
    ['🌤️ 天气', ['北京天气', '上海天气呢', '杭州明天会下雨吗']],
    ['🛣️ 路线', ['北京到上海自驾路线', '广州到成都怎么去', '福州到杭州3日自驾游']],
    ['🎡 游玩', ['上海四日游', '去新疆玩', '漳州好玩景点']],
    ['🍡 美食', ['成都美食推荐', '广州早茶去哪吃', '厦门小吃推荐']],
    ['🚄 交通', ['广州到成都机票', '福州到漳州火车票', '北京到西安高铁']],
];

function renderWelcome() {
    const div = document.createElement('div');
    div.className = 'welcome';
    let lis = '';
    WELCOME_ITEMS.forEach(([cat, qs]) => {
        const links = qs.map(q => `<a data-q="${q}">${q}</a>`).join(' / ');
        lis += `<li><b>${cat}：</b>${links}</li>`;
    });
    div.innerHTML = '<h3>🌸 你好呀～我是你的专属旅行小精灵 🧳</h3>' +
        '<p>想去哪里玩？点下面的小问题，我马上帮你安排 💕</p><ul>' + lis + '</ul>';
    div.querySelectorAll('a[data-q]').forEach(a => {
        a.onclick = () => { userInput.value = a.dataset.q; sendMessage(); };
    });
    chatBox.appendChild(div);
}

/* ---------------- 消息渲染 ---------------- */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    // 优先用 marked + DOMPurify，加载失败时降级为纯文本
    if (window.marked) {
        try {
            const raw = window.marked.parse(text, { breaks: true, gfm: true });
            if (window.DOMPurify) return window.DOMPurify.sanitize(raw);
            return raw;
        } catch (e) { /* fallthrough */ }
    }
    return '<p style="white-space:pre-wrap">' + escapeHtml(text) + '</p>';
}

/**
 * 添加一条消息
 * @param text 消息文本（agent 消息支持 markdown）
 * @param isUser 是否用户消息
 * @param isHistory 是否历史回放（回放时直接整体渲染，不流式）
 */
function addMessage(text, isUser = false, isHistory = false) {
    const div = document.createElement('div');
    div.className = `msg ${isUser ? 'user' : 'agent'}`;

    const bubble = document.createElement('div');
    bubble.className = 'bubble' + (isUser ? '' : ' md');

    if (isUser) {
        bubble.textContent = text;
    } else if (isHistory) {
        bubble.innerHTML = renderMarkdown(text);
    } else {
        // 流式消息：状态提示行 + 正文容器
        const statusArea = document.createElement('div');
        statusArea.className = 'status-area';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        contentDiv.innerHTML = '<span class="thinking">✨ 正在为你规划美好旅程<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></span>';
        bubble.appendChild(statusArea);
        bubble.appendChild(contentDiv);
        div._statusArea = statusArea;
        div._content = contentDiv;
    }

    div.appendChild(bubble);
    chatBox.appendChild(div);
    scrollToBottom();
    return div;
}

function addStatusLine(msgDiv, text) {
    if (!msgDiv || !msgDiv._statusArea) return;
    const line = document.createElement('div');
    line.className = 'status-line';
    line.textContent = text;
    msgDiv._statusArea.appendChild(line);
    scrollToBottom();
}

function scrollToBottom() {
    chatBox.scrollTop = chatBox.scrollHeight;
}

/* 图片加载失败时隐藏，避免裂图 */
chatBox.addEventListener('error', function (e) {
    if (e.target && e.target.tagName === 'IMG') e.target.style.display = 'none';
}, true);

/* ---------------- 发送消息（SSE 流式） ---------------- */

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || sending) return;

    sending = true;
    sendBtn.disabled = true;
    userInput.value = '';

    // 移除欢迎卡片（如有）
    const welcome = chatBox.querySelector('.welcome');
    if (welcome) welcome.remove();

    // 1. 用户气泡
    addMessage(text, true);

    // 2. 确保会话存在
    if (!currentConvId) {
        const conv = { id: Date.now().toString(), title: text.slice(0, 18) || '新对话', messages: [] };
        conversations.unshift(conv);
        currentConvId = conv.id;
    }
    const conv = currentConv();
    conv.messages.push({ role: 'user', content: text });

    // 3. 智能体流式气泡
    const agentDiv = addMessage('');
    let rawText = '';

    try {
        const res = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, user_id: 'web_user' }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // 解析 SSE 帧：data: {...}\n\n
            const frames = buffer.split('\n\n');
            buffer = frames.pop();
            for (const frame of frames) {
                const line = frame.trim();
                if (!line.startsWith('data:')) continue;
                let payload;
                try { payload = JSON.parse(line.slice(5).trim()); }
                catch (e) { continue; }

                if (payload.type === 'delta' && payload.content) {
                    rawText += payload.content;
                    // 流式过程中用纯文本增量展示，结束后整体渲染 Markdown
                    agentDiv._content.innerHTML =
                        '<p style="white-space:pre-wrap">' + escapeHtml(rawText) + '</p>';
                    scrollToBottom();
                } else if (payload.type === 'status') {
                    addStatusLine(agentDiv, payload.content);
                } else if (payload.type === 'map_update' && payload.map) {
                    // 地图联动：路线绘制 / POI撒点 / 视角聚焦
                    if (window.TravelMap) TravelMap.apply(payload.map);
                } else if (payload.type === 'error') {
                    rawText += '\n\n**' + payload.content + '**';
                } else if (payload.type === 'done') {
                    agentDiv._content.innerHTML = renderMarkdown(rawText || '（智能体未返回内容）');
                }
            }
        }
        // 兜底：没有收到 done 帧也渲染
        agentDiv._content.innerHTML = renderMarkdown(rawText || '（智能体未返回内容）');
    } catch (err) {
        agentDiv._content.innerHTML = renderMarkdown(
            (rawText ? rawText + '\n\n' : '') + '**请求失败：' + err.message + '，请确认后端服务已启动。**'
        );
    } finally {
        conv.messages.push({ role: 'agent', content: rawText || '（智能体未返回内容）' });
        saveConversations();
        renderConvList();
        sending = false;
        sendBtn.disabled = false;
        scrollToBottom();
    }
}

/* 回车发送 */
userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') sendMessage();
});

/* 初始化 */
renderConvList();
if (!currentConvId) renderWelcome();
userInput.focus();
