
// solo se ejecuta si  
//{{ $('step_2_sanitize_plan').first().json.intent }} es matchRegex (search_articles|search_chunks|summarize|compare_viewpoints|backgrounder)
// y {{  $('step_2_sanitize_plan').first().json.queryText is notEmpty }}
return [{  
    ... $('step_2_sanitize_plan').first().json,    
    embedding: $input.first().json.data[0].embedding  //$input.first().json.data[0].embedding es el la respuesta del http request a OpenAI que esta en en nodo anterior
}];
