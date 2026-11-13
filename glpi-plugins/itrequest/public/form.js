(() => {
  const type = document.getElementById('request-type');
  const email = document.getElementById('email-service');
  if (!type || !email) return;
  const update = () => {
    document.querySelectorAll('[data-request-types]').forEach(section => {
      section.hidden = !section.dataset.requestTypes.split(' ').includes(type.value);
    });
    document.querySelectorAll('[data-email-services]').forEach(section => {
      section.hidden = !section.dataset.emailServices.split(' ').includes(email.value);
    });
    // Inactive fields must not trigger browser validation or submit unrelated data.
    document.querySelectorAll('[data-request-types] input, [data-request-types] select, [data-email-services] input').forEach(input => {
      input.disabled = !!input.closest('[hidden]');
    });
  };
  type.addEventListener('change', update);
  email.addEventListener('change', update);
  update();
})();
