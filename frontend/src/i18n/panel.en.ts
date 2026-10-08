import type { Dict } from "./ar";

const panel: Dict["panel"] = {
  nav: {
    groupMessages: "Conversations",
    groupTrain: "Train the bot",
    groupSetup: "Settings",
    home: "Home",
    handoffs: "Handoffs",
    inbox: "Inbox",
    test: "Test",
    more: "More",
    main: "Panel menu",
    closeMenu: "Close menu",
  },

  dashboard: {
    greeting: (name) => `Hi, ${name}`,
    offHint: "Turn it on so it can talk to your customers.",
    quickTitle: "Shortcuts",
    quick: {
      playground: { title: "Test the bot", body: "Ask as a customer and see the reply." },
      knowledge: { title: "Shop info", body: "The more complete, the better the replies." },
      inbox: { title: "Inbox", body: "Recent customer conversations." },
      settings: { title: "Tone and rules", body: "How the bot talks and what it never does." },
    },
    usageTitle: "This month's usage",
  },

  knowledge: {
    navTitle: "Sections",
    filled: "Filled",
    empty: "Empty",
    drop: "Drop a file here",
    or: "or",
    choose: "Choose file",
  },

  playground: {
    env: "Test mode",
    botName: (shop) => `${shop} bot`,
    tipsTitle: "What should I try?",
    tips: ["Questions customers ask all the time", "Stock or price of a specific product", "Something you haven't told the bot"],
    safe: "Nothing is sent to anyone or saved, and it works even while the bot is off.",
    improveTitle: "Make the replies better",
  },

  settings: {
    sections: {
      status: { title: "Status", desc: "Turn Replisto on or off for all conversations." },
      identity: { title: "Introduction", desc: "The name the bot introduces itself with." },
      tone: { title: "Tone", desc: "How the bot talks to customers. See a sample of each." },
      fallback: { title: "When it doesn't know", desc: "The message sent while the conversation is handed to you." },
      rules: { title: "Rules", desc: "Lines the bot never crosses." },
      handoff: { title: "When you reply yourself", desc: "The bot stays quiet for that customer for a while so it doesn't talk over you." },
    },
    discard: "Discard",
    sample: "Sample",
  },

  instagram: {
    stepsTitle: "Two things before connecting",
    howItWorks: "You connect through Instagram's official page; no page password needed.",
  },

  notFound: {
    hint: "This page doesn't exist or has moved.",
  },
};

export default panel;
