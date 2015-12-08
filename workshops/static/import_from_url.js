$('#import_url_button').click(function() {
  $('#import_url_modal').modal();
});
$('#import_url_form').submit(function(e) {
  e.preventDefault();

  // indicate loading data
  var btn = $(this).find('button[type=submit]');
  btn.attr('disabled', true);

  var url = $(this).find(':input[name=url]').val();

  // load data from URL
  $.post("/workshops/events/import/", $(this).find(":input"), function(data) {
    $("#event_import_url").parent().removeClass('has-error');
    $('#import_url_modal').modal('hide');
    $('#error_message').addClass('hidden');

    $("#id_slug").val(data.slug);
    $("#id_start").val(data.start);
    $("#id_end").val(data.end);
    $("#id_reg_key").val(data.reg_key);
    $("#id_url").val(url);
    $("#id_contact").val(data.contact);
    $('#id_venue').val(data.venue);
    $('#id_address').val(data.address);
    $('#id_country').val(data.country);
    $('#id_latitude').val(data.latitude);
    $('#id_longitude').val(data.longitude);

    $("#id_notes").val(
      "INSTRUCTORS: " + data.instructors.join(", ") + "\n\n" +
      "HELPERS: " + data.helpers.join(", ")
    );
  })
  .fail(function(data) {
    // something went wrong, let's indicate it
    $("#event_import_url").parent().addClass('has-error');
    $('#error_message').text(data.responseText);
    $('#error_message').removeClass('hidden');
  })
  .always(function(data) {
    // let's always reenable the form's submit when the request finishes
    btn.attr('disabled', false);
  });
});
