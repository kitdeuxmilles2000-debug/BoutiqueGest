(function () {
  var prefix = 'boutiquegest:form:';
  var hasError = !!document.querySelector('.alerts .alert.danger, .alerts .alert.warning');
  var forms = document.querySelectorAll('form[data-preserve-on-error]');

  function getValues(values, name) {
    return values[name] || [];
  }

  function growDynamicRows(values) {
    var saleRows = document.querySelectorAll('#sale_unit_rows .sale-unit-row');
    var saleCount = getValues(values, 'sale_unit_type').length;
    while (saleRows.length < saleCount && typeof window.addSaleUnit === 'function') {
      window.addSaleUnit();
      saleRows = document.querySelectorAll('#sale_unit_rows .sale-unit-row');
    }

    var newSaleRows = document.querySelectorAll('#new_sale_unit_rows .sale-unit-row');
    var newSaleCount = getValues(values, 'new_sale_unit_type').length;
    while (newSaleRows.length < newSaleCount && typeof window.addNewSaleUnit === 'function') {
      window.addNewSaleUnit();
      newSaleRows = document.querySelectorAll('#new_sale_unit_rows .sale-unit-row');
    }
  }

  function restoreForm(form, saved) {
    var values = saved.values || {};
    var productId = getValues(values, 'product_id')[0];
    var preset = getValues(values, 'new_preset_type')[0];
    var presetField = form.querySelector('[name="new_preset_type"]');
    if (presetField && preset) presetField.value = preset.value;

    if (productId && productId.value && typeof window.selectProduct === 'function') {
      window.selectProduct(productId.value);
    }

    var newProductToggle = form.querySelector('#toggle_new_product');
    var savedNewProduct = getValues(values, 'toggle_new_product')[0];
    if (newProductToggle && savedNewProduct && savedNewProduct.checked && typeof window.toggleNewProduct === 'function') {
      newProductToggle.checked = true;
      window.toggleNewProduct();
    }

    growDynamicRows(values);

    var positions = {};
    Array.prototype.forEach.call(form.querySelectorAll('[name]'), function (field) {
      var name = field.name;
      var entries = getValues(values, name);
      if (!entries.length) return;
      var position = positions[name] || 0;
      positions[name] = position + 1;
      var entry = entries[position];
      if (!entry) return;
      if (field.type === 'checkbox' || field.type === 'radio') {
        field.checked = !!entry.checked;
      } else {
        field.value = entry.value;
      }
    });

    if (form.querySelector('#allow_mod') && form.querySelector('#allow_mod').checked && typeof window.toggleMod === 'function') {
      window.toggleMod();
    }
    if (typeof window.filterProducts === 'function') window.filterProducts();
    if (typeof window.updateExistingQtyPreview === 'function') window.updateExistingQtyPreview();
    if (typeof window.syncNewIntakeCost === 'function') window.syncNewIntakeCost();

    var modal = form.closest('.modal');
    if (modal) modal.classList.add('show');
  }

  if (!hasError) {
    Object.keys(sessionStorage).forEach(function (key) {
      if (key.indexOf(prefix) === 0) sessionStorage.removeItem(key);
    });
  }

  Array.prototype.forEach.call(forms, function (form) {
    var key = prefix + window.location.pathname + ':' + (form.dataset.preserveKey || 'form');
    if (hasError) {
      try {
        var saved = JSON.parse(sessionStorage.getItem(key) || 'null');
        if (saved && Date.now() - saved.timestamp < 15 * 60 * 1000) {
          if (saved.action) form.action = saved.action;
          restoreForm(form, saved);
          sessionStorage.removeItem(key);
        }
      } catch (error) {
        sessionStorage.removeItem(key);
      }
    }

    form.addEventListener('submit', function () {
      var values = {};
      Array.prototype.forEach.call(form.querySelectorAll('[name]'), function (field) {
        if (!field.name || field.type === 'password' || /password|csrf|token|form_version/i.test(field.name)) return;
        if (!values[field.name]) values[field.name] = [];
        values[field.name].push({ value: field.value, checked: !!field.checked });
      });
      try {
        sessionStorage.setItem(key, JSON.stringify({
          timestamp: Date.now(),
          action: form.action,
          values: values
        }));
      } catch (error) {
        return;
      }
    }, true);
  });
})();