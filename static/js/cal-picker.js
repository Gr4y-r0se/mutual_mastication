/* Admin poll creation — interactive date picker calendar */

var MONTH_NAMES = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December'
];

var selectedDates = new Set();
var viewYear  = new Date().getFullYear();
var viewMonth = new Date().getMonth(); // 0-based

function daysInMonth(y, m) {
  return new Date(y, m + 1, 0).getDate();
}

// Monday-based weekday index for the 1st of a month (0=Mon, 6=Sun)
function firstWeekday(y, m) {
  return (new Date(y, m, 1).getDay() + 6) % 7;
}

function fmtDate(y, m, d) {
  return y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
}

function renderCal() {
  document.getElementById('cal-month-label').textContent =
    MONTH_NAMES[viewMonth] + ' ' + viewYear;

  var tbody = document.getElementById('cal-picker-body');
  var first = firstWeekday(viewYear, viewMonth);
  var total = daysInMonth(viewYear, viewMonth);
  var today = new Date();

  var html = '';
  var day = 1;
  for (var week = 0; week < 6; week++) {
    if (day > total) break;
    html += '<tr>';
    for (var wd = 0; wd < 7; wd++) {
      if (week === 0 && wd < first) {
        html += '<td class="cal-cell cal-empty"></td>';
      } else if (day > total) {
        html += '<td class="cal-cell cal-empty"></td>';
      } else {
        var ds  = fmtDate(viewYear, viewMonth, day);
        var sel = selectedDates.has(ds);
        var isPast = new Date(viewYear, viewMonth, day) <
                     new Date(today.getFullYear(), today.getMonth(), today.getDate());
        html += '<td class="cal-picker-cell'
          + (sel    ? ' cal-picker-selected' : '')
          + (isPast ? ' cal-picker-past'     : '')
          + '" onclick="toggleDate(\'' + ds + '\')">'
          + day + '</td>';
        day++;
      }
    }
    html += '</tr>';
  }
  tbody.innerHTML = html;

  var sorted  = Array.from(selectedDates).sort();
  var summary = document.getElementById('cal-summary');
  summary.textContent = sorted.length === 0
    ? 'No dates selected.'
    : sorted.length + ' date(s) selected: ' + sorted.join(', ');

  document.getElementById('options').value = sorted.join('\n');
}

function toggleDate(ds) {
  if (selectedDates.has(ds)) {
    selectedDates.delete(ds);
  } else {
    selectedDates.add(ds);
  }
  renderCal();
}

function calPrev() {
  if (viewMonth === 0) { viewMonth = 11; viewYear--; } else viewMonth--;
  renderCal();
}

function calNext() {
  if (viewMonth === 11) { viewMonth = 0; viewYear++; } else viewMonth++;
  renderCal();
}

function onTypeChange() {
  var t = document.getElementById('poll_type').value;
  document.getElementById('date-picker').style.display       = t === 'date'       ? 'block' : 'none';
  document.getElementById('restaurant-picker').style.display = t === 'restaurant' ? 'block' : 'none';
  var vm = document.getElementById('vote_mode');
  if (t === 'date'       && vm.value === 'approval') vm.value = 'approval';
  if (t === 'date'       && vm.value === 'single')   vm.value = 'approval';
  if (t === 'restaurant' && vm.value === 'approval') vm.value = 'single';
}

document.addEventListener('DOMContentLoaded', function() {
  renderCal();
  onTypeChange();
});
