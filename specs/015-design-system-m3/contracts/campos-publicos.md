# Contrato: campos dos formulários públicos (entrega 3, decisão Q2)

## Onde vale

Rótulo flutuante (`campo campo-flutuante`), nas telas que o público usa:

- `pedidos/_formulario.html`: nome completo, destino (ou número da viatura) e nº da ocorrência;
- `pedidos/consulta.html`: número do pedido e primeiro nome;
- `contas/entrar.html`: matrícula e senha. A tela é **uma só para a equipe e o solicitante**, tem
  layout próprio (estende o `base.html`, com o `contas/css/entrar.css`) e fica inteira na entrega 3,
  com o rótulo flutuante para todos (`FormularioEntrada`);
- `contas/trocar_senha.html`, que já usa o `base_publico.html` (`FormularioTrocaSenha`);
- `contas/bloqueado.html` (429 do limite de tentativas) não tem campo, mas entra nas capturas.

Fica de fora:

- a busca de materiais: continua a pílula, com o exemplo dentro;
- as observações: o rótulo é o título do passo (`aria-labelledby`); recebem só a caixa nova;
- as quantidades: a do resultado, a do carrinho e a da folha;
- os campos das telas da área interna (`base_almoxarifado.html`), que mantêm o rótulo fixo acima.

## Markup

```html
<div class="campo campo-flutuante{% if erros %} campo-com-erro{% endif %}">
  <label class="campo-rotulo" for="destino">Destino dos materiais</label>
  <div class="com-acao">
    <input id="destino" class="campo-entrada" name="destino" placeholder=" "
           aria-describedby="{% if erros %}destino-erro{% else %}destino-dica{% endif %}" …>
    …botão Limpar de hoje…
  </div>
  {% if not erros %}<p id="destino-dica" class="campo-dica">Setor ou posto de trabalho</p>{% endif %}
  {% include "pedidos/_erro_campo.html" %}                                {# o de hoje #}
</div>
```

- A ordem (label antes do campo) e as classes de hoje continuam. Só entram o modificador
  `campo-flutuante`, o `placeholder=" "` e o `campo-dica` com o texto que era o placeholder
  (`fluxo.exemplo_destino`; nos outros campos, a dica que já existe).
- **Com erro, a dica sai do HTML e do `aria-describedby`**, e o `campo-erro` (com ícone) toma o
  lugar dela. Um elemento citado no `aria-describedby` é lido mesmo escondido por CSS, então
  esconder não basta.
- O botão "Limpar" continua dentro do campo, à direita.
- **Login e troca de senha**: os campos vêm de `{% for campo in form %}`. O `placeholder=" "` e a
  classe entram pelos widgets de `FormularioEntrada` e `FormularioTrocaSenha` (`contas/forms.py`).
  O `FormularioEntradaAdmin` (login do admin) não muda.

## Estados (CSS)

| Estado | Rótulo | Caixa |
|---|---|---|
| Vazio, sem foco (com `:has()`) | dentro da caixa, 16px, `--texto-secundario` | `--contorno` 1px |
| Com foco | na borda, 12px, `--destaque` | `--destaque` 2px |
| Preenchido, sem foco | na borda, 12px, `--texto-secundario` | `--contorno` 1px |
| Com erro | na borda, `--erro-forte` | `--erro-forte` 2px |
| Navegador sem `:has()` | sempre na borda | conforme o estado |

"Preenchido" inclui o **preenchimento automático do navegador**: o seletor do rótulo dentro da caixa
exclui `:autofill` e `:-webkit-autofill` além de exigir `:placeholder-shown`. O Chrome preenche a
matrícula e a senha antes de o campo deixar de ser `:placeholder-shown`, e sem a exclusão o rótulo
ficaria por cima do texto.

## Comportamento que não muda

- O `pedidos.js` lembra o nome e o destino no aparelho e preenche só campos vazios. O rótulo sobe
  porque o campo deixa de estar `:placeholder-shown`, sem script.
- O resumo de erros do topo, com o link para o campo e o foco nele.
- O `dropdown.js` monta a lista de destinos (`input[list]`). O revisor conferiu que o campo visível
  continua o mesmo elemento, dentro do `.campo`, e que o `:placeholder-shown` vale nele. Fica para a
  captura conferir se a lista aberta não cobre o rótulo flutuado.

## Documentação que muda junto (entrega 3)

O `CLAUDE.md` descreve o `Fluxo.exemplo_destino` como "o placeholder do destino" (parágrafo da spec
007). No mesmo PR, passa a "o texto de apoio do destino".

## Testes (entrega 3)

- O markup de cada campo da lista "Onde vale": `campo-flutuante`, `placeholder=" "`, o `campo-dica`
  com o texto do antigo placeholder e o `aria-describedby`. Por fluxo: o `exemplo_destino` de limpeza,
  viaturas, oficina e EPIs, e o padrão do `Fluxo` ("Setor, posto ou placa") no AB.
- Com erro: `aria-invalid="true"`, o `campo-erro`, nenhum `campo-dica`, e o `aria-describedby` só com
  o id do erro.
- O login e a troca de senha: os widgets com `placeholder=" "`; o login do admin sem mudança.
- A busca de materiais continua com o `placeholder` do exemplo (`fluxo.exemplo_busca`).
