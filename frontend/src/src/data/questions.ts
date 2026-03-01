import { Question, Archetype, CoreParameters } from '../types/game';

export const INITIAL_PARAMS: CoreParameters = {
  cooperationBias: 50,
  deceptionTendency: 50,
  strategicHorizon: 50,
  riskAppetite: 50
};

export const QUESTIONS: Question[] = [
{
  id: 1,
  text: "Запрошення приносить кур'єр без обличчя. Чорний конверт, неонова печатка Короля Рейву. Чому ти? Що ти робиш?",
  answers: [
  {
    id: '1a',
    text: 'Одягаєшся найкраще і їдеш одразу. Такі запрошення не повторюються.',
    effects: { riskAppetite: 10, cooperationBias: 5 }
  },
  {
    id: '1b',
    text: 'Шукаєш інформацію про Короля Рейву. Хто він? Чому саме ти?',
    effects: { strategicHorizon: 15, riskAppetite: -5 }
  },
  {
    id: '1c',
    text: 'Береш із собою когось, кому не кажеш куди ви їдете.',
    effects: { deceptionTendency: 10, strategicHorizon: 5 }
  }]

},
{
  id: 2,
  text: 'На вході охоронець каже: "Залишилось одне місце". За тобою плаче людина, якій "життєво необхідно" потрапити всередину.',
  answers: [
  {
    id: '2a',
    text: 'Пропускаєш незнайомця. Ввічливість — найкраща маска.',
    effects: { cooperationBias: 15, deceptionTendency: 5 }
  },
  {
    id: '2b',
    text: 'Заходиш сам. Тебе запросили, їх — ні.',
    effects: { cooperationBias: -10, riskAppetite: 10 }
  },
  {
    id: '2c',
    text: 'Кажеш охоронцю, що ви разом. Блефуєш.',
    effects: { deceptionTendency: 15, riskAppetite: 10 }
  }]

},
{
  id: 3,
  text: 'Всередині ти помічаєш людину з минулого, яка тебе зрадила. Вона тебе ще не бачить.',
  answers: [
  {
    id: '3a',
    text: 'Підходиш з посмішкою. Нехай нервують, гадаючи що ти знаєш.',
    effects: { deceptionTendency: 10, strategicHorizon: 10 }
  },
  {
    id: '3b',
    text: 'Ігноруєш. Минуле — це минуле.',
    effects: { strategicHorizon: 5, riskAppetite: -5 }
  },
  {
    id: '3c',
    text: 'Розповідаєш першому-ліпшому хто ця людина насправді.',
    effects: {
      riskAppetite: 15,
      cooperationBias: -10,
      deceptionTendency: 5
    }
  },
  {
    id: '3d',
    text: 'Тримаєш дистанцію, але спостерігаєш. Інформація — це валюта.',
    effects: { strategicHorizon: 20, deceptionTendency: 5 }
  }]

},
{
  id: 4,
  text: 'На танцполі незнайомець непомітно суне тобі в руку записку: "Не довіряй тому, хто в червоному".',
  answers: [
  {
    id: '4a',
    text: 'Шукаєш людину в червоному. Попередження — це вже інформація.',
    effects: { strategicHorizon: 10, riskAppetite: 5 }
  },
  {
    id: '4b',
    text: 'Знаходиш того, хто дав записку. Хочеш знати навіщо.',
    effects: { strategicHorizon: 15, cooperationBias: -5 }
  },
  {
    id: '4c',
    text: 'Ігноруєш. Маніпуляції починаються з довіри до незнайомців.',
    effects: { deceptionTendency: -5, riskAppetite: 10 }
  }]

},
{
  id: 5,
  text: 'Хтось пропонує тобі випити з пляшки, до якої сам ще не торкався.',
  answers: [
  {
    id: '5a',
    text: "П'єш не вагаючись. Страх — це слабкість, яку тут відчувають.",
    effects: { riskAppetite: 20, strategicHorizon: -10 }
  },
  {
    id: '5b',
    text: 'Дякуєш, але наливаєш собі сам з тієї ж пляшки.',
    effects: { strategicHorizon: 10, deceptionTendency: 5 }
  }]

},
{
  id: 6,
  text: 'Впливова компанія запрошує тебе за свій стіл. Але щоб сісти, ти маєш публічно висміяти когось за сусіднім.',
  answers: [
  {
    id: '6a',
    text: 'Сідаєш і кажеш щось дотепне, але не жорстоке. Баланс.',
    effects: {
      deceptionTendency: 10,
      cooperationBias: 5,
      strategicHorizon: 5
    }
  },
  {
    id: '6b',
    text: 'Відмовляєшся. Повага не продається за місце за столом.',
    effects: {
      cooperationBias: 15,
      deceptionTendency: -10,
      riskAppetite: -5
    }
  },
  {
    id: '6c',
    text: 'Висміюєш так, що весь зал сміється. Влада — це увага.',
    effects: {
      riskAppetite: 15,
      deceptionTendency: 15,
      cooperationBias: -15
    }
  }]

},
{
  id: 7,
  text: 'У VIP-коридорі ти випадково чуєш план публічного приниження Короля Рейву.',
  answers: [
  {
    id: '7a',
    text: 'Попереджаєш Короля. Лояльність — це інвестиція.',
    effects: {
      cooperationBias: 15,
      strategicHorizon: 10,
      deceptionTendency: -5
    }
  },
  {
    id: '7b',
    text: 'Мовчиш і чекаєш. Хай грають свою гру.',
    effects: { strategicHorizon: 10, cooperationBias: -5 }
  },
  {
    id: '7c',
    text: 'Приєднуєшся до змови. Королі падають, а ти будеш поруч з новою владою.',
    effects: {
      riskAppetite: 20,
      deceptionTendency: 15,
      cooperationBias: -20
    }
  },
  {
    id: '7d',
    text: 'Продаєш інформацію обом сторонам.',
    effects: {
      deceptionTendency: 25,
      strategicHorizon: 10,
      cooperationBias: -15
    }
  }]

},
{
  id: 8,
  text: 'Людина, з якою ти спілкувався весь вечір, просить потримати її важку сумку "на 5 хвилин". Вона виглядає наляканою.',
  answers: [
  {
    id: '8a',
    text: 'Береш без питань. Довіра будується на ризику.',
    effects: { cooperationBias: 15, riskAppetite: 10 }
  },
  {
    id: '8b',
    text: 'Питаєш що всередині. Сліпа довіра — це не довіра.',
    effects: { strategicHorizon: 10, cooperationBias: -5 }
  },
  {
    id: '8c',
    text: "Відмовляєшся м'яко. Чужі проблеми — це пастка.",
    effects: {
      cooperationBias: -10,
      strategicHorizon: 10,
      riskAppetite: -5
    }
  }]

},
{
  id: 9,
  text: 'Король Рейву особисто запрошує тебе до приватної кімнати. Твого нового друга не запросили, і він виглядає ображеним.',
  answers: [
  {
    id: '9a',
    text: 'Просиш взяти друга з собою. Або обоє, або ніхто.',
    effects: {
      cooperationBias: 20,
      strategicHorizon: -10,
      riskAppetite: 5
    }
  },
  {
    id: '9b',
    text: 'Йдеш сам. Пояснюєш потім. Можливості не чекають.',
    effects: {
      cooperationBias: -10,
      strategicHorizon: 15,
      riskAppetite: 5
    }
  },
  {
    id: '9c',
    text: 'Йдеш, але обіцяєш другу розповісти все. Не факт, що розкажеш.',
    effects: { deceptionTendency: 15, strategicHorizon: 10 }
  }]

},
{
  id: 10,
  text: 'Король Рейву пропонує угоду: розкрий чийсь секрет, який ти дізнався сьогодні, за постійне місце за його столом.',
  answers: [
  {
    id: '10a',
    text: 'Відмовляєшся. Деякі речі не продаються.',
    effects: {
      cooperationBias: 20,
      deceptionTendency: -15,
      riskAppetite: -10
    }
  },
  {
    id: '10b',
    text: 'Розповідаєш. Секрети — це валюта, а ти тут щоб торгувати.',
    effects: {
      deceptionTendency: 20,
      strategicHorizon: 10,
      cooperationBias: -20
    }
  },
  {
    id: '10c',
    text: 'Вигадуєш секрет. Даєш Королю те, що він хоче, не зраджуючи нікого.',
    effects: {
      deceptionTendency: 25,
      riskAppetite: 15,
      strategicHorizon: 5
    }
  }]

},
{
  id: 11,
  text: 'Світло гасне. Коли вмикається, зникає щось дуже цінне. Всі дивляться на тебе.',
  answers: [
  {
    id: '11a',
    text: 'Спокійно кажеш: "Обшукайте мене. Мені нема чого ховати".',
    effects: {
      cooperationBias: 15,
      deceptionTendency: -5,
      riskAppetite: 10
    }
  },
  {
    id: '11b',
    text: 'Вказуєш на когось іншого. Найкращий захист — це атака.',
    effects: {
      deceptionTendency: 20,
      riskAppetite: 10,
      cooperationBias: -15
    }
  },
  {
    id: '11c',
    text: 'Мовчиш. Хай думають що хочуть. Виправдання — це слабкість.',
    effects: { strategicHorizon: 15, riskAppetite: 10 }
  },
  {
    id: '11d',
    text: 'Пропонуєш допомогти знайти. Контролюєш розслідування зсередини.',
    effects: {
      strategicHorizon: 15,
      deceptionTendency: 10,
      cooperationBias: 5
    }
  }]

},
{
  id: 12,
  text: 'Світанок. Вечірка закінчується. Король Рейву спостерігає, як ти йдеш. Як ти покидаєш зал?',
  answers: [
  {
    id: '12a',
    text: 'Тихо, через чорний хід. Ніхто не повинен знати що ти тут був.',
    effects: { strategicHorizon: 15, deceptionTendency: 10 }
  },
  {
    id: '12b',
    text: "Через головний вхід, попрощавшись з усіма. Зв'язки — це все.",
    effects: { cooperationBias: 15, strategicHorizon: 5 }
  },
  {
    id: '12c',
    text: 'Залишаєшся останнім. Ранок — це коли починається справжня гра.',
    effects: {
      riskAppetite: 20,
      strategicHorizon: 10,
      cooperationBias: -5
    }
  }]

}];


export const ARCHETYPES: Archetype[] = [
{
  name: 'ТІНЬ',
  description:
  'Ти рухаєшся непомітно. Люди довіряють тобі свої секрети — і це їхня найбільша помилка. Ти не зраджуєш. Ти просто граєш краще за всіх.',
  condition: (p) => p.deceptionTendency > 65 && p.cooperationBias < 45
},
{
  name: 'ЛЯЛЬКОВОД',
  description:
  'Навіщо бруднити руки, якщо інші зроблять все за тебе? Ти бачиш нитки, за які можна смикати, і ніхто навіть не підозрює, хто насправді керує вечіркою.',
  condition: (p) => p.strategicHorizon > 70 && p.deceptionTendency > 60
},
{
  name: 'АДРЕНАЛІН',
  description:
  'Хаос — це твій кисень. Ти ставиш все на зеро і смієшся, коли рулетка крутиться. Для тебе це не виживання, це розвага.',
  condition: (p) => p.riskAppetite > 75 && p.strategicHorizon < 50
},
{
  name: 'ДИПЛОМАТ',
  description:
  'Твоя зброя — це емпатія. Ти знаєш, що справжня влада тримається на союзах, а не на страху. Але чи вистачить тобі жорстокості, коли прийде час?',
  condition: (p) => p.cooperationBias > 70 && p.deceptionTendency < 50
},
{
  name: 'ХИЖАК',
  description:
  'Ти не прийшов сюди заводити друзів. Ти прийшов забирати своє. Високий ризик, нуль довіри. Ти — хижак у кімнаті, повній здобичі.',
  condition: (p) =>
  p.riskAppetite > 65 && p.deceptionTendency > 60 && p.cooperationBias < 40
},
{
  name: 'ГРАВЕЦЬ',
  description:
  'Збалансований, адаптивний, небезпечний. Ти робиш те, що потрібно, тоді, коли це потрібно. Нічого особистого, тільки бізнес.',
  condition: () => true
}];


export const getBackgroundClass = (questionId: number): string => {
  if (questionId <= 3) return 'bg-entrance';
  if (questionId <= 6) return 'bg-dancefloor';
  if (questionId <= 9) return 'bg-vip';
  return 'bg-throne';
};