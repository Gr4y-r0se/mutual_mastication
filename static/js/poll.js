/* Poll page — calendar vote toggle, vote-card sync, voter tooltip */

// Calendar date cell toggle (date polls)
function toggleVote(optionId, isSingle) {
  var input = document.getElementById('opt-' + optionId);
  var cell  = document.getElementById('cell-' + optionId);
  if (!input || !cell) return;

  if (isSingle) {
    var wasChecked = input.checked;
    document.querySelectorAll('input[type=radio][name=option_id]').forEach(function(r) {
      r.checked = false;
      var c = document.getElementById('cell-' + r.value);
      if (c) c.classList.remove('cal-voted');
    });
    if (!wasChecked) {
      input.checked = true;
      cell.classList.add('cal-voted');
    }
  } else {
    input.checked = !input.checked;
    cell.classList.toggle('cal-voted', input.checked);
  }
}

// Sync vote-card selected state when an input changes
document.querySelectorAll('.vote-card input').forEach(function(input) {
  input.addEventListener('change', function() {
    if (this.type === 'radio') {
      document.querySelectorAll('.vote-card input[name="' + this.name + '"]').forEach(function(r) {
        r.closest('.vote-card').classList.toggle('vote-card--on', r.checked);
      });
    } else {
      this.closest('.vote-card').classList.toggle('vote-card--on', this.checked);
    }
  });
});

// Voter hover tooltip
(function() {
  var tip = document.getElementById('voter-tooltip');
  if (!tip) return;
  document.querySelectorAll('[data-voters]').forEach(function(el) {
    el.addEventListener('mouseenter', function() {
      var v = el.dataset.voters;
      if (!v) return;
      tip.textContent = v;
      tip.classList.add('visible');
    });
    el.addEventListener('mousemove', function(e) {
      tip.style.left = (e.clientX + 14) + 'px';
      tip.style.top  = (e.clientY - 36) + 'px';
    });
    el.addEventListener('mouseleave', function() {
      tip.classList.remove('visible');
    });
  });
})();
