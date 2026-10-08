import { execFile } from 'child_process';

export function sleep(seconds) {
  return new Promise((resolve) => {
    setTimeout(resolve, seconds * 1000);
  });
}

export function log(message) {
  console.log(`[${new Date().toISOString()}]`, message);
}

// Fires a macOS notification (terminal-notifier if present, otherwise osascript) so a
// found date doesn't just sit unseen in a background log. Never throws - a notification
// failure should not take down the polling loop, but it is logged so it is not silent.
function escapeAppleScript(str) {
  return String(str).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

export function notify(title, message) {
  execFile('terminal-notifier', ['-title', title, '-message', message, '-sound', 'Glass'], (err) => {
    if (!err) return;
    const script = `display notification "${escapeAppleScript(message)}" with title "${escapeAppleScript(title)}" sound name "Glass"`;
    execFile('osascript', ['-e', script], (osaErr) => {
      if (osaErr) {
        log(`Notification failed (terminal-notifier: ${err.message}; osascript: ${osaErr.message})`);
      }
    });
  });
}

export function isSocketHangupError(err) {
  return err.code === 'ECONNRESET' || 
         err.code === 'ENOTFOUND' || 
         err.code === 'ETIMEDOUT' ||
         err.message.includes('socket hang up') ||
         err.message.includes('network') ||
         err.message.includes('connection');
}