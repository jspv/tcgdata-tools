<table>
{% for key, value in result.items() %}
   <tr>
        <th> {{ key }} </th>
        <td> {{ value }} </td>
   </tr>
{% endfor %}
</table>
