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
      resultDiv.innerHTML = '';
      var dot = document.createElement('span');
      dot.className = 'health-dot ' + (resp.ok ? 'green' : 'red');
      var msg = document.createElement('span');
      msg.className = 'form-hint';
      msg.textContent = resp.ok ? (data.message || 'done') : (data.message || 'failed');
      resultDiv.appendChild(dot);
      resultDiv.appendChild(document.createTextNode(' '));
      resultDiv.appendChild(msg);
    } catch(err) {
      resultDiv.innerHTML = '';
      var dot = document.createElement('span');
      dot.className = 'health-dot red';
      var msg = document.createElement('span');
      msg.className = 'form-hint';
      msg.textContent = 'request failed';
      resultDiv.appendChild(dot);
      resultDiv.appendChild(document.createTextNode(' '));
      resultDiv.appendChild(msg);
    }
  });
});
