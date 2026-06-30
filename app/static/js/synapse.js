/* ================================================================
   PROJECT SYNAPSE — Main JavaScript File
   ================================================================
   Modules:
   1.  Behaviour Tracker       — logs all student interactions
   2.  Quiz Engine             — timer, selection, submission
   3.  AI Tutor Interface      — explain, summarise, revise
   4.  Dashboard Charts        — Chart.js setup helpers
   5.  Recommendation Actions  — mark acted-on
   6.  Lesson Progress         — time tracking, mark complete
   7.  Admin Tools             — experiment recording
   8.  Toast Notifications     — global alert system
   9.  Form Helpers            — validation, UX
   10. Utility Functions       — shared helpers
   ================================================================ */

'use strict';

/* ================================================================
   GLOBAL CSRF HELPER
   Defined first, before any module, so every module below
   (SynapseQuiz, SynapseAI, SynapseLesson, SynapseTracker, etc.)
   can call getCsrfToken() directly without errors.
   This is the ONLY place the meta tag is read from.
   ================================================================ */
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}


/* ================================================================
   1. BEHAVIOUR TRACKER
   Automatically tracks lesson open, close, clicks, time, revisits.
   Sends data to /student/track via sendBeacon on page unload.
   ================================================================ */
const SynapseTracker = (() => {
  let startTime     = Date.now();
  let clickCount    = 0;
  let scrollDepth   = 0;
  let isTracking    = false;
  let lessonId      = null;
  let idleTimer     = null;
  let idleThreshold = 60000; // 1 minute idle = log inactivity

  function init() {
    lessonId = document.body.dataset.lessonId
      ? parseInt(document.body.dataset.lessonId)
      : null;

    if (!lessonId) return;
    isTracking = true;
    startTime  = Date.now();

    // Click tracking
    document.addEventListener('click', () => {
      clickCount++;
      resetIdleTimer();
    });

    // Scroll depth tracking
    document.addEventListener('scroll', () => {
      const depth = Math.round(
        (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
      );
      scrollDepth = Math.max(scrollDepth, depth || 0);
      resetIdleTimer();
    });

    // Idle detection
    document.addEventListener('mousemove', resetIdleTimer);
    document.addEventListener('keypress', resetIdleTimer);
    resetIdleTimer();

    // Log lesson open
    postTrack({
      lesson_id:   lessonId,
      action_type: 'lesson_open',
      duration:    0,
      clicks:      0,
    });

    // Log revisit if returning
    const visitKey = `synapse_visited_${lessonId}`;
    if (localStorage.getItem(visitKey)) {
      postTrack({ lesson_id: lessonId, action_type: 'revisit' });
    }
    localStorage.setItem(visitKey, '1');

    // On page leave — log close with full session data
    window.addEventListener('beforeunload', () => {
      const duration = Math.floor((Date.now() - startTime) / 1000);
      navigator.sendBeacon('/student/track', JSON.stringify({
        lesson_id:    lessonId,
        action_type:  'lesson_close',
        duration:     duration,
        clicks:       clickCount,
        metadata:     { scroll_depth: scrollDepth },
      }));
    });
  }

  function resetIdleTimer() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (isTracking && lessonId) {
        postTrack({ lesson_id: lessonId, action_type: 'idle', duration: idleThreshold / 1000 });
      }
    }, idleThreshold);
  }

  function postTrack(data) {
    fetch('/student/track', {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify(data),
    }).catch(() => {});  // Silent fail — tracking is best-effort
  }

  return { init, postTrack };
})();


/* ================================================================
   2. QUIZ ENGINE
   Handles option selection, timer countdown, submission + results.
   ================================================================ */
const SynapseQuiz = (() => {
  let answers       = {};
  let startTime     = null;
  let timerInterval = null;
  let totalQuestions = 0;
  let quizId        = null;
  let submitted     = false;

  function init(qId, total) {
    quizId         = qId;
    totalQuestions = total;
    startTime      = Date.now();
    answers        = {};

    startTimer();
    updateProgress();
  }

  /* ── Timer ───────────────────────────────────────────────── */
  function startTimer() {
    const display = document.getElementById('timerDisplay');
    if (!display) return;
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const mins    = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const secs    = String(elapsed % 60).padStart(2, '0');
      display.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
  }

  /* ── Option Selection ────────────────────────────────────── */
  function selectOption(el) {
    if (submitted) return;
    const qid = el.dataset.qid;
    // Deselect all options for this question
    document.querySelectorAll(`[data-qid="${qid}"]`)
      .forEach(o => o.classList.remove('selected'));
    // Select clicked option
    el.classList.add('selected');
    answers[qid] = el.dataset.opt;
    updateProgress();
  }

  /* ── Progress Bar ────────────────────────────────────────── */
  function updateProgress() {
    const answered = Object.keys(answers).length;
    const pct      = totalQuestions ? (answered / totalQuestions * 100) : 0;
    const bar      = document.getElementById('progressBar');
    const text     = document.getElementById('progressText');
    if (bar)  bar.style.width  = pct + '%';
    if (text) text.textContent = `${answered} / ${totalQuestions} answered`;
  }

  /* ── Submit Quiz ─────────────────────────────────────────── */
  function submit() {
    if (submitted) return;
    const unanswered = totalQuestions - Object.keys(answers).length;
    if (unanswered > 0) {
      const ok = confirm(
        `You have ${unanswered} unanswered question${unanswered > 1 ? 's' : ''}.\nSubmit anyway?`
      );
      if (!ok) return;
    }

    submitted = true;
    stopTimer();
    const timeTaken = Math.floor((Date.now() - startTime) / 1000);

    // Show loading state on submit button
    const submitBtn = document.getElementById('submitBtn')
      || document.querySelector('[onclick="submitQuiz()"]');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting…';
    }

    fetch(`/student/quiz/${quizId}/submit`, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify({ answers, time_taken: timeTaken }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        showResults(data, timeTaken);
      } else {
        SynapseToast.show('Submission failed. Please try again.', 'danger');
        submitted = false;
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="bi bi-check2-circle me-2"></i>Submit Quiz';
        }
      }
    })
    .catch((err) => {
      console.error('Quiz submit error:', err);
      SynapseToast.show('Network error. Check your connection.', 'danger');
      submitted = false;
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-check2-circle me-2"></i>Submit Quiz';
      }
    });
  }

  /* ── Show Results ────────────────────────────────────────── */
  function showResults(data, timeTaken) {
    const formEl   = document.getElementById('quizForm');
    const resultEl = document.getElementById('resultBox');
    if (formEl)   formEl.classList.add('d-none');
    if (resultEl) resultEl.classList.remove('d-none');

    // Populate result values
    _setText('resultScore',  `${data.score.toFixed(1)}%`);
    _setText('correctCount', data.correct);
    _setText('wrongCount',   data.wrong);
    _setText('timeCount',    timeTaken);
    _setText('resultDetail', `${data.correct} correct out of ${data.total} questions`);

    // Icon + message based on score
    const icon  = document.getElementById('resultIcon');
    const msgEl = document.getElementById('resultMessage');

    if (data.score >= 80) {
      if (icon)  icon.innerHTML = '<i class="bi bi-trophy-fill text-warning" style="font-size:3.5rem;"></i>';
      if (msgEl) {
        msgEl.className = 'alert alert-success mb-4';
        msgEl.innerHTML = '<i class="bi bi-check-circle-fill me-2"></i>'
          + '<strong>Outstanding!</strong> Excellent performance. Your AI tutor has updated your recommendations.';
      }
    } else if (data.score >= 60) {
      if (icon)  icon.innerHTML = '<i class="bi bi-patch-check-fill text-primary" style="font-size:3.5rem;"></i>';
      if (msgEl) {
        msgEl.className = 'alert alert-primary mb-4';
        msgEl.innerHTML = '<i class="bi bi-info-circle-fill me-2"></i>'
          + '<strong>Good work!</strong> Keep practising to improve further.';
      }
    } else if (data.score >= 40) {
      if (icon)  icon.innerHTML = '<i class="bi bi-emoji-neutral-fill text-warning" style="font-size:3.5rem;"></i>';
      if (msgEl) {
        msgEl.className = 'alert alert-warning mb-4';
        msgEl.innerHTML = '<i class="bi bi-arrow-repeat me-2"></i>'
          + '<strong>Keep going!</strong> Revision materials have been recommended for you.';
      }
    } else {
      if (icon)  icon.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-danger" style="font-size:3.5rem;"></i>';
      if (msgEl) {
        msgEl.className = 'alert alert-danger mb-4';
        msgEl.innerHTML = '<i class="bi bi-robot me-2"></i>'
          + '<strong>Don\'t give up!</strong> Your AI tutor has prepared targeted revision for you.';
      }
    }

    // Scroll to result
    if (resultEl) resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ── Private ─────────────────────────────────────────────── */
  function _setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  return { init, selectOption, submit, updateProgress };
})();


/* ================================================================
   3. AI TUTOR INTERFACE
   Handles all AI interactions: explain, summarise, revision notes.
   ================================================================ */
const SynapseAI = (() => {
  let modal = null;

  function init() {
    const modalEl = document.getElementById('aiModal');
    if (modalEl) {
      modal = new bootstrap.Modal(modalEl);
    }
  }

  /* ── Open AI modal ───────────────────────────────────────── */
  function openTutor(prefillTopic = '') {
    if (!modal) init();
    if (prefillTopic) {
      const input = document.getElementById('aiTopicInput');
      if (input) input.value = prefillTopic;
    }
    if (modal) modal.show();
  }

  /* ── Explain a topic ─────────────────────────────────────── */
  function explain(lessonId = null) {
    const topic = _getInputVal('aiTopicInput');
    if (!topic) {
      SynapseToast.show('Please enter a topic to explain.', 'warning');
      return;
    }
    _callAI('/ai/explain', { topic, lesson_id: lessonId }, 'aiResponseBox', 'aiResponseText', 'aiLoadingBox');
  }

  /* ── Summarise a lesson ──────────────────────────────────── */
  function summarise(lessonId) {
    if (!lessonId) {
      SynapseToast.show('Missing lesson reference. Refresh the page and try again.', 'warning');
      return;
    }
    _callAI(
      '/ai/summary',
      { lesson_id: lessonId },
      'summaryBox', 'summaryText', 'summaryLoading',
      true
    );
  }

  /* ── Get revision notes ──────────────────────────────────── */
  function getRevisionNotes(courseTitle) {
    const box = document.getElementById('revisionBox');
    if (box) { box.classList.remove('d-none'); box.style.display = ''; }
    _callAI(
      '/ai/revision-notes',
      { course_title: courseTitle || 'Your Course' },
      'revisionBox', 'revisionText', 'revisionLoading'
    );
  }

  /* ── Generate AI quiz ────────────────────────────────────── */
  function generateQuiz(topic, containerEl) {
    if (!topic || !containerEl) return;
    const box = document.getElementById(containerEl);
    if (box) {
      box.innerHTML = '<div class="text-center py-3"><span class="spinner-border spinner-border-sm text-primary me-2"></span>Generating questions…</div>';
    }
    fetch('/ai/generate-quiz', {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify({ topic }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.success && data.questions.length) {
        _renderAIQuiz(data.questions, containerEl);
      } else {
        if (box) box.innerHTML = '<p class="text-muted small">Could not generate questions. Try again.</p>';
      }
    })
    .catch(() => {
      if (box) box.innerHTML = '<p class="text-danger small">AI service unavailable.</p>';
    });
  }

  /* ── Render AI-generated questions ──────────────────────── */
  function _renderAIQuiz(questions, containerId) {
    const box = document.getElementById(containerId);
    if (!box) return;
    let html = '<div class="mt-3">';
    questions.forEach((q, i) => {
      html += `
        <div class="mb-3 p-3 rounded" style="background:var(--bg-card2);border:1.5px solid var(--border);">
          <p class="fw-semibold mb-2 small">${i + 1}. ${_escapeHtml(q.question)}</p>
          ${(q.options || []).map(opt => `
            <div class="small text-secondary py-1 px-2">
              <i class="bi bi-circle me-2" style="font-size:0.65rem;"></i>${_escapeHtml(opt)}
            </div>
          `).join('')}
          <div class="mt-2 small text-success fw-semibold">
            <i class="bi bi-check-circle-fill me-1"></i>Answer: ${_escapeHtml(q.correct || '')}
          </div>
        </div>`;
    });
    html += '</div>';
    box.innerHTML = html;
  }

  /* ── Core AI fetch helper ────────────────────────────────── */
  function _callAI(endpoint, payload, boxId, textId, loadingId, appendToBox = false) {
    const box     = document.getElementById(boxId);
    const textEl  = document.getElementById(textId);
    const loading = document.getElementById(loadingId);

    if (box)     box.classList.remove('d-none');
    if (loading) loading.classList.remove('d-none');
    if (textEl && !appendToBox) textEl.innerHTML = '';

    fetch(endpoint, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify(payload),
    })
    .then(r => r.json())
    .then(data => {
      if (loading) loading.classList.add('d-none');
      if (data.success) {
        const formatted = _formatAIResponse(data.response);
        if (textEl) textEl.innerHTML = formatted;
        if (box) box.classList.remove('d-none');
      } else {
        if (textEl) textEl.innerHTML = `<span class="text-danger small">Error: ${_escapeHtml(data.error || 'Unknown error')}</span>`;
        SynapseToast.show('AI request failed. Check your API key.', 'danger');
      }
    })
    .catch((err) => {
      console.error('AI call failed:', endpoint, err);
      if (loading) loading.classList.add('d-none');
      if (textEl)  textEl.innerHTML = '<span class="text-danger small">AI service unavailable. Check your OPENAI_API_KEY in .env</span>';
    });
  }

  /* ── Format AI markdown-ish response to HTML ─────────────── */
  function _formatAIResponse(text) {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      // Bold: **text**
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      // Italic: *text*
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      // Bullet points: lines starting with - or •
      .replace(/^[\-•]\s+(.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>)/s, '<ul class="mt-2 mb-2">$1</ul>')
      // Numbered lists: 1. text
      .replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')
      // Headers: ### text
      .replace(/^###\s+(.+)$/gm, '<h6 class="fw-bold text-primary mt-3 mb-1">$1</h6>')
      .replace(/^##\s+(.+)$/gm, '<h6 class="fw-bold mt-3 mb-1">$1</h6>')
      // Line breaks
      .replace(/\n\n/g, '</p><p class="mb-2">')
      .replace(/\n/g, '<br>');
  }

  function _getInputVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  }

  function _escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { init, openTutor, explain, summarise, getRevisionNotes, generateQuiz };
})();


/* ================================================================
   4. DASHBOARD CHARTS
   Chart.js helper functions used across student + admin dashboards.
   ================================================================ */
const SynapseCharts = (() => {

  /* ── Line Chart — Quiz Progress ─────────────────────────── */
  function renderProgressChart(canvasId) {
    fetch('/analytics/student/progress')
      .then(r => r.json())
      .then(data => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (!data.length) {
          canvas.closest('.synapse-card-body').innerHTML =
            '<p class="text-muted small text-center py-4">'
            + '<i class="bi bi-bar-chart-line me-2"></i>'
            + 'No quiz data yet. Complete a quiz to see your progress.</p>';
          return;
        }
        new Chart(canvas.getContext('2d'), {
          type: 'line',
          data: {
            labels:   data.map(d => d.date),
            datasets: [{
              label:           'Quiz Score (%)',
              data:            data.map(d => d.score),
              borderColor:     '#2563EB',
              backgroundColor: 'rgba(37,99,235,0.08)',
              fill:            true,
              tension:         0.45,
              pointRadius:     5,
              pointHoverRadius: 7,
              pointBackgroundColor: '#2563EB',
              pointBorderColor:     '#fff',
              pointBorderWidth:     2,
            }]
          },
          options: {
            responsive: true,
            plugins: {
              legend:  { display: false },
              tooltip: {
                backgroundColor: '#1E293B',
                titleColor:      '#E4E6EB',
                bodyColor:       '#94A3B8',
                padding:         10,
                cornerRadius:    8,
                callbacks: {
                  label: ctx => ` Score: ${ctx.parsed.y.toFixed(1)}%`
                }
              }
            },
            scales: {
              y: {
                min: 0, max: 100,
                ticks: { callback: v => v + '%', color: '#94A3B8' },
                grid:  { color: 'rgba(0,0,0,0.05)' },
              },
              x: {
                ticks: { color: '#94A3B8', maxTicksLimit: 8 },
                grid:  { display: false },
              }
            }
          }
        });
      })
      .catch(() => {});
  }

  /* ── Radar Chart — Topic Performance ────────────────────── */
  function renderTopicChart(canvasId) {
    fetch('/analytics/student/topics')
      .then(r => r.json())
      .then(data => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !data.length) return;
        new Chart(canvas.getContext('2d'), {
          type: 'radar',
          data: {
            labels:   data.map(d => d.topic),
            datasets: [{
              label:           'Avg Score',
              data:            data.map(d => d.avg_score),
              backgroundColor: 'rgba(124,58,237,0.15)',
              borderColor:     '#7C3AED',
              pointBackgroundColor: '#7C3AED',
              pointBorderColor:     '#fff',
              pointBorderWidth:     2,
              pointRadius:     4,
            }]
          },
          options: {
            responsive: true,
            scales: {
              r: {
                min:       0,
                max:       100,
                ticks:     { display: false },
                grid:      { color: 'rgba(0,0,0,0.08)' },
                pointLabels: { font: { size: 11, weight: '600' }, color: '#475569' }
              }
            },
            plugins: { legend: { display: false } }
          }
        });
      })
      .catch(() => {});
  }

  /* ── Bar Chart — A/B Experiment ─────────────────────────── */
  function renderABChart(canvasId) {
    fetch('/analytics/admin/ab-test')
      .then(r => r.json())
      .then(d => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        new Chart(canvas.getContext('2d'), {
          type: 'bar',
          data: {
            labels: ['Avg Score', 'Engagement', 'Completion'],
            datasets: [
              {
                label:           'Control',
                data:            [d.control?.avg_score || 0, d.control?.avg_engagement || 0, d.control?.avg_completion || 0],
                backgroundColor: 'rgba(5,150,105,0.7)',
                borderColor:     '#059669',
                borderWidth:     2,
                borderRadius:    6,
              },
              {
                label:           'Experimental',
                data:            [d.experimental?.avg_score || 0, d.experimental?.avg_engagement || 0, d.experimental?.avg_completion || 0],
                backgroundColor: 'rgba(37,99,235,0.7)',
                borderColor:     '#2563EB',
                borderWidth:     2,
                borderRadius:    6,
              }
            ]
          },
          options: {
            responsive: true,
            scales: {
              y: {
                min: 0, max: 100,
                ticks:  { callback: v => v + '%', color: '#94A3B8' },
                grid:   { color: 'rgba(0,0,0,0.06)' },
              },
              x: { ticks: { color: '#94A3B8' }, grid: { display: false } }
            },
            plugins: {
              legend: { labels: { color: '#475569', font: { weight: '600' } } },
              tooltip: { backgroundColor: '#1E293B', titleColor: '#E4E6EB', bodyColor: '#94A3B8', cornerRadius: 8 }
            }
          }
        });
      })
      .catch(() => {});
  }

  /* ── Line Chart — Engagement Trend (Admin) ───────────────── */
  function renderEngagementChart(canvasId, days = 30) {
    fetch(`/analytics/admin/engagement-trend?days=${days}`)
      .then(r => r.json())
      .then(d => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        new Chart(canvas.getContext('2d'), {
          type: 'line',
          data: {
            labels:   d.map(x => x.date),
            datasets: [{
              label:           'Active Users',
              data:            d.map(x => x.active_users),
              borderColor:     '#0EA5E9',
              backgroundColor: 'rgba(14,165,233,0.08)',
              fill:            true,
              tension:         0.4,
              pointRadius:     3,
              pointBackgroundColor: '#0EA5E9',
            }]
          },
          options: {
            responsive: true,
            scales: {
              y: { ticks: { color: '#94A3B8' }, grid: { color: 'rgba(0,0,0,0.05)' } },
              x: { ticks: { color: '#94A3B8', maxTicksLimit: 10 }, grid: { display: false } }
            },
            plugins: { legend: { display: false } }
          }
        });
      })
      .catch(() => {});
  }

  return { renderProgressChart, renderTopicChart, renderABChart, renderEngagementChart };
})();


/* ================================================================
   5. RECOMMENDATION ACTIONS
   ================================================================ */
const SynapseRecommendations = (() => {

  function filterByType(type, btnEl) {
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('btn-primary', 'active');
      b.classList.add('btn-outline-secondary');
    });
    if (btnEl) {
      btnEl.classList.add('btn-primary', 'active');
      btnEl.classList.remove('btn-outline-secondary');
    }
    // Show / hide items
    document.querySelectorAll('.rec-item').forEach(item => {
      item.style.display = (type === 'all' || item.dataset.type === type) ? '' : 'none';
    });
  }

  return { filterByType };
})();


/* ================================================================
   6. LESSON PROGRESS TRACKER
   Tracks time on a lesson page and sends completion.
   ================================================================ */
const SynapseLesson = (() => {
  let lessonStartTime = Date.now();
  let clickCount      = 0;

  function init() {
    document.addEventListener('click', () => clickCount++);
  }

  function markComplete(lessonId) {
    if (!lessonId) {
      SynapseToast.show('Missing lesson reference. Refresh the page and try again.', 'warning');
      return;
    }

    const duration = Math.floor((Date.now() - lessonStartTime) / 1000);
    const btn      = document.querySelector('[onclick*="markComplete"]');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving…';
    }

    fetch(`/student/lesson/${lessonId}/complete`, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify({ time_spent: duration, clicks: clickCount }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        if (btn) {
          btn.innerHTML = '<i class="bi bi-check-circle-fill me-2"></i>Completed!';
          btn.classList.replace('btn-outline-success', 'btn-success');
        }
        SynapseToast.show('Lesson marked as complete!', 'success');
      } else {
        SynapseToast.show('Could not save progress.', 'danger');
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="bi bi-check-circle me-1"></i>Mark Complete';
        }
      }
    })
    .catch(() => {
      SynapseToast.show('Could not save progress.', 'danger');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-circle me-1"></i>Mark Complete';
      }
    });
  }

  return { init, markComplete };
})();


/* ================================================================
   7. ADMIN TOOLS
   Experiment recording and admin-specific actions.
   ================================================================ */
const SynapseAdmin = (() => {

  function recordExperiment(userId, preScore, postScore) {
    fetch('/admin/experiment/record', {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body:    JSON.stringify({
        user_id:         userId,
        pre_test_score:  parseFloat(preScore)  || 0,
        post_test_score: parseFloat(postScore) || 0,
      }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) SynapseToast.show('Experiment result saved!', 'success');
      else              SynapseToast.show('Failed to save result.', 'danger');
    })
    .catch(() => SynapseToast.show('Network error.', 'danger'));
  }

  function searchStudents(query) {
    const rows = document.querySelectorAll('tbody tr');
    const q    = query.toLowerCase();
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(q) ? '' : 'none';
    });
  }

  return { recordExperiment, searchStudents };
})();


/* ================================================================
   8. TOAST NOTIFICATIONS
   Global non-blocking alert system.
   ================================================================ */
const SynapseToast = (() => {
  const icons = {
    success: 'bi-check-circle-fill',
    danger:  'bi-x-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info:    'bi-info-circle-fill',
  };

  function show(message, type = 'info', duration = 3500) {
    // Create container if not present
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.cssText = 'position:fixed;top:72px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:340px;';
      document.body.appendChild(container);
    }

    const toastEl = document.createElement('div');
    toastEl.style.cssText = `
      background:#fff;
      border:1.5px solid var(--border);
      border-left:4px solid var(--${type === 'danger' ? 'danger' : type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'primary'});
      border-radius:10px;
      padding:12px 16px;
      font-size:0.875rem;
      font-weight:500;
      color:var(--text-primary);
      box-shadow:0 4px 20px rgba(0,0,0,0.12);
      display:flex;
      align-items:center;
      gap:10px;
      animation:fadeInUp 0.3s ease;
    `;

    const colorMap = { success: '#059669', danger: '#DC2626', warning: '#EA580C', info: '#2563EB' };
    const icon     = icons[type] || icons.info;
    const color    = colorMap[type] || colorMap.info;

    toastEl.innerHTML = `
      <i class="bi ${icon}" style="color:${color};font-size:1rem;flex-shrink:0;"></i>
      <span style="flex-grow:1;">${message}</span>
      <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:#94A3B8;font-size:1rem;line-height:1;padding:0;">×</button>
    `;

    container.appendChild(toastEl);
    setTimeout(() => {
      toastEl.style.transition = 'opacity 0.3s, transform 0.3s';
      toastEl.style.opacity    = '0';
      toastEl.style.transform  = 'translateX(20px)';
      setTimeout(() => toastEl.remove(), 300);
    }, duration);
  }

  return { show };
})();


/* ================================================================
   9. FORM HELPERS
   Client-side UX improvements for forms.
   ================================================================ */
const SynapseForms = (() => {

  // Show/hide password toggle
  function togglePassword(inputId, btnEl) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isText = input.type === 'text';
    input.type   = isText ? 'password' : 'text';
    if (btnEl) {
      btnEl.querySelector('i').className = isText
        ? 'bi bi-eye' : 'bi bi-eye-slash';
    }
  }

  // Live character counter for textareas
  function addCharCounter(textareaId, maxLength) {
    const ta = document.getElementById(textareaId);
    if (!ta) return;
    const counter = document.createElement('div');
    counter.className = 'form-text text-end';
    counter.textContent = `0 / ${maxLength}`;
    ta.parentNode.appendChild(counter);
    ta.addEventListener('input', () => {
      const len = ta.value.length;
      counter.textContent = `${len} / ${maxLength}`;
      counter.style.color = len > maxLength * 0.9 ? 'var(--warning)' : 'var(--text-muted)';
    });
  }

  // Auto-resize textarea
  function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  // Attach auto-resize to all matching textareas
  function initAutoResize() {
    document.querySelectorAll('textarea.synapse-input').forEach(ta => {
      ta.addEventListener('input', () => autoResize(ta));
    });
  }

  return { togglePassword, addCharCounter, autoResize, initAutoResize };
})();


/* ================================================================
   10. UTILITY FUNCTIONS
   Shared helpers used across modules.
   (getCsrfToken lives at the very top of this file now —
   not duplicated here to avoid the bug we just fixed.)
   ================================================================ */
const SynapseUtils = (() => {

  // POST with CSRF header
  function post(url, data) {
    return fetch(url, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken':  getCsrfToken(),
      },
      body: JSON.stringify(data),
    }).then(r => r.json());
  }

  // Format seconds to mm:ss string
  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  // Debounce helper
  function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  // Format date string nicely
  function formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  // Copy text to clipboard
  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
      SynapseToast.show('Copied to clipboard!', 'success', 2000);
    });
  }

  return { post, formatTime, debounce, formatDate, copyToClipboard };
})();


/* ================================================================
   GLOBAL SHORTCUT FUNCTIONS
   These are called directly from HTML onclick attributes.
   ================================================================ */

// AI Tutor shortcuts
function requestAITutor()       { SynapseAI.openTutor(); }
function explainTopic(topic)    { SynapseAI.openTutor(topic); }
function callAIExplain(lid)     { SynapseAI.explain(lid || null); }
function getAISummary(lid)      { SynapseAI.summarise(lid); }
function getRevisionNotes(title){ SynapseAI.getRevisionNotes(title); }

// Quiz shortcuts
function selectOption(el)       { SynapseQuiz.selectOption(el); }
function submitQuiz()           { SynapseQuiz.submit(); }

// Lesson shortcuts
function markComplete(lid)      { SynapseLesson.markComplete(lid); }

// Recommendation filter shortcut
function filterRecs(type, btn)  { SynapseRecommendations.filterByType(type, btn); }

// Admin shortcut
function searchStudents(q)      { SynapseAdmin.searchStudents(q); }


/* ================================================================
   AUTO-INIT ON DOM READY
   ================================================================ */
document.addEventListener('DOMContentLoaded', () => {

  // Start behaviour tracker (only runs if data-lesson-id is set on body)
  SynapseTracker.init();

  // Init AI modal if present
  SynapseAI.init();

  // Init lesson progress tracking
  SynapseLesson.init();

  // Init form auto-resize
  SynapseForms.initAutoResize();

  // Auto-init quiz if quiz page
  const quizIdEl = document.getElementById('quizId');
  const totalEl  = document.getElementById('totalQuestions');
  if (quizIdEl && totalEl) {
    SynapseQuiz.init(
      parseInt(quizIdEl.value),
      parseInt(totalEl.value)
    );
  }

  // Auto-init dashboard charts if on student dashboard
  if (document.getElementById('progressChart')) {
    SynapseCharts.renderProgressChart('progressChart');
  }
  if (document.getElementById('topicChart')) {
    SynapseCharts.renderTopicChart('topicChart');
  }

  // Auto-init admin charts if on admin dashboard
  if (document.getElementById('abChart')) {
    SynapseCharts.renderABChart('abChart');
  }
  if (document.getElementById('engagementChart')) {
    SynapseCharts.renderEngagementChart('engagementChart');
  }

  // Admin student search box
  const searchBox = document.getElementById('studentSearchBox');
  if (searchBox) {
    searchBox.addEventListener('input', SynapseUtils.debounce(e => {
      SynapseAdmin.searchStudents(e.target.value);
    }, 250));
  }

  // Highlight active nav link based on current URL
  const currentPath = window.location.pathname;
  document.querySelectorAll('.synapse-navbar .nav-link').forEach(link => {
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });

  // Add smooth scroll to all anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', e => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // Auto-dismiss flash alerts after 5 seconds
  document.querySelectorAll('.synapse-alert.alert-dismissible').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

});