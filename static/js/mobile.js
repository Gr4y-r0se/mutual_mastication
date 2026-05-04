/* Mobile — wrap data tables in a horizontal scroll container */
document.querySelectorAll('main table:not(.cal-table)').forEach(function(t) {
  var w = document.createElement('div');
  w.className = 'tbl-scroll';
  t.parentNode.insertBefore(w, t);
  w.appendChild(t);
});
