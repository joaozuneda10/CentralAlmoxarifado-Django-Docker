# Contrato: campos dos formulários públicos (entrega 3, decisão Q2)

## Onde vale

Rótulo flutuante (`campo campo-flutuante`):

- `_formulario.html`: nome completo, destino (ou número da viatura) e nº da ocorrência;
- `consulta.html`: número do pedido e primeiro nome;
- `contas/entrar.html`, no login de solicitante: matrícula e senha;
- troca de senha do solicitante (spec 013), se estiver no layout público.

Fica de fora:

- a busca de materiais: continua a pílula, com o exemplo dentro;
- as observações: o rótulo é o título do passo (`aria-labelledby`); recebem só a caixa nova;
- as quantidades: a do resultado, a do carrinho e a da folha;
- todos os campos da área interna, que mantêm o rótulo fixo acima.

## Markup

```html
<div class="campo campo-flutuante{% if erros %} campo-com-erro{% endif %}">
  <label class="campo-rotulo" for="destino">Destino dos materiais</label>
  <div class="com-acao">
    <input id="destino" class="campo-entrada" name="destino" placeholder=" "
           aria-describedby="destino-dica{% if erros %} destino-erro{% endif %}" …>
    …botão Limpar de hoje…
  </div>
  <p id="destino-dica" class="campo-dica">Setor ou posto de trabalho</p>   {# o antigo placeholder #}
  {% include "pedidos/_erro_campo.html" %}                                {# o de hoje #}
</div>
```

- A ordem (label antes do campo) e as classes de hoje continuam. Só entram o modificador
  `campo-flutuante`, o `placeholder=" "` e o `campo-dica` com o texto que era o placeholder
  (`fluxo.exemplo_destino`; nos outros campos, a dica que já existe).
- Com erro, o `campo-dica` fica escondido e o `campo-erro` (com ícone) toma o lugar dele. O
  `aria-describedby` aponta para os dois; o escondido não é lido.
- O botão "Limpar" continua dentro do campo, à direita.

## Estados (CSS)

| Estado | Rótulo | Caixa |
|---|---|---|
| Vazio, sem foco (com `:has()`) | dentro da caixa, 16px, `--texto-secundario` | `--contorno` 1px |
| Com foco | na borda, 12px, `--destaque` | `--destaque` 2px |
| Preenchido, sem foco | na borda, 12px, `--texto-secundario` | `--contorno` 1px |
| Com erro | na borda, `--erro-forte` | `--erro-forte` 2px |
| Navegador sem `:has()` | sempre na borda | conforme o estado |

## Comportamento que não muda

- O `pedidos.js` lembra o nome e o destino no aparelho e preenche só campos vazios. O rótulo sobe
  porque o campo deixa de estar `:placeholder-shown`, sem script.
- O resumo de erros do topo, com o link para o campo e o foco nele.
- O `dropdown.js` monta a lista de destinos (`input[list]`). A conferir: o campo visível fica dentro
  do `.campo`, e a lista não cobre o rótulo flutuado (research R4).

## Testes (entrega 3)

- O markup de cada campo da lista "Onde vale": `campo-flutuante`, `placeholder=" "`, o `campo-dica`
  com o texto do antigo placeholder (por fluxo: `exemplo_destino` de limpeza, viaturas, oficina e EPIs)
  e o `aria-describedby`.
- Com erro: `aria-invalid="true"`, o `campo-erro` e o `aria-describedby` com as duas ligações.
- A busca de materiais continua com o `placeholder` do exemplo (`fluxo.exemplo_busca`).
