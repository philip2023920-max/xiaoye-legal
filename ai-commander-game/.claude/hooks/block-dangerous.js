// .claude/hooks/block-dangerous.js — 老闆的實體護欄（ai-dev-team v2.4）
// 純文字比對的絆線：寧可誤擋、不可漏放。被擋時不准繞過或換寫法重試。
const fs = require('fs');
let input = {};
try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch (e) { process.exit(0); }
const cmd = String((input.tool_input && input.tool_input.command) || '');
const RULES = [
  [/git\s+reset\s+--hard/i, 'git reset --hard 會丟掉還沒存檔的修改'],
  [/git\s+clean\s+-[a-z]*f/i, 'git clean -f 會刪掉還沒被 git 追蹤的檔案'],
  [/git\s+(checkout|restore)\s+(\.(\s|$|\/)|--\s)/i, 'checkout . / restore . 會用舊版覆蓋還沒存檔的修改'],
  [/git\s+branch\s+-D\b/, 'branch -D 會強制刪掉分支'],  // 刻意區分大小寫：小寫 -d 是安全刪除，不擋
  [/git\s+push\b[^\n]*(\s--force\b|\s-f\b)/i, '強制推送會覆蓋遠端歷史'],
  [/\b(Set-Content|Add-Content)\b(?![^\n]*-Encoding\s+utf8)/i, 'PowerShell 寫檔沒帶 -Encoding utf8 會弄壞中文檔；改文字檔請用編輯工具'],
];
for (const [re, why] of RULES) {
  if (re.test(cmd)) {
    console.error('⛔ 老闆的護欄擋下了這條指令：' + why + '。不准繞過或換寫法重試；請改用安全替代（git stash／開新分支／從指定 commit 還原單一檔案），或直接問老闆。');
    process.exit(2);
  }
}
process.exit(0);
