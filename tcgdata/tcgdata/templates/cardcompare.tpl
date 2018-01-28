{% macro render_field(field) %}
<dt>{{ field.label }}
  <dd>{{ field(**kwargs)|safe }}
  {% if field.errors %}
    <ul class=errors>
    {% for error in field.errors %}
      <li>{{ error }}</li>
    {% endfor %}
    </ul>
  {% endif %}
  </dd>
{% endmacro %}

{% macro with_errors(field) %}
    <div class="form_field">
    {% if field.errors %}
        {% set css_class = 'has_error ' + kwargs.pop('class', '') %}
        {{ field(class=css_class, **kwargs) }}
        <ul class="errors">{% for error in field.errors %}<li>{{ error|e }}</li>{% endfor %}</ul>
    {% else %}
        {{ field(**kwargs) }}
    {% endif %}
    </div>
{% endmacro %}

<!DOCTYPE html>
<html lang="en">

<title>Compare Cards</title>
<link rel=stylesheet type=text/css href="{{ url_for('static', filename='style.css')  }}">

<body>
  <div class=page>
    <h1> Compare Cards </h1>
    <table>
      <tr>
        <td></td>
        <td> {{ card0.id }} </td>
        <td> {{ card1.id }} </td>
      </tr>
      <tr>
        <td></td>
        <td> <img src=" {{ url_for( 'static', filename=image0) }} " /> </td>
        <td> <img src="{{ url_for( 'static', filename=image1) }} " /> </td>
      </tr>
      <form method="POST" action="{{ url_for('process_compareform') }}">
        {{ form.csrf_token }}
      {% for key, value in diffs.items() %}
      <tr>
        <th> {{ key }} [{{ value[0].index }}]
          <p>Fuzz={{ value[0].score }} </th>
        {% for i in form|attr(key) %}
        <td> {{i}} {{ i.label }} </td>
        {% endfor %}
      </tr>
      {% endfor %}
      <tr>
        <!-- <th> Flag for Later Detailed Review </th>
        {% for element in form.flag_for_edits %}
          <td> {{ element }} {{ element.label }}</td>
        {% endfor%} -->
    </table>
        {{ form.process_changes }}
        {{ form.no_match }}
        {{ form.quit }}
        {{ form.forcematch }}
    </form>

  <body>
