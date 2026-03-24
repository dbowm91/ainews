document.addEventListener('DOMContentLoaded', function() {
  var form = document.getElementById('dry-run-form');
  if (!form) return;
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    var email = form.querySelector('input[name="test_email"]').value;
    var csrf = form.querySelector('input[name="csrf_token"]').value;
    var resultDiv = document.getElementById('dry-run-result');
    resultDiv.innerHTML = '<span class="form-hint">sending dry run...</span>';
    try {
      var resp = await fetch(form.action, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'test_email=' + encodeURIComponent(email) + '&csrf_token=' + encodeURIComponent(csrf)
      });
      var data = await resp.json();
      if (resp.ok) {
        resultDiv.innerHTML = '<span class="health-dot green"></span> <span class="form-hint">' + data.message + '</span>';
      } else {
        resultDiv.innerHTML = '<span class="health-dot red"></span> <span class="form-hint">' + (data.message || 'failed') + '</span>';
      }
    } catch(err) {
      resultDiv.innerHTML = '<span class="health-dot red"></span> <span class="form-hint">request failed</span>';
    }
  });
});
